// Package scenario holds config parsing shared by the single and multi scenarios.
package scenario

import (
	"encoding/json"
	"fmt"
	"regexp"
	"strconv"
	"strings"
)

type Service struct {
	Name  string            `json:"name"`
	Image string            `json:"image"`
	Port  int               `json:"port,omitempty"`
	Entry bool              `json:"entry,omitempty"`
	Env   map[string]string `json:"env,omitempty"`
}

type Common struct {
	Protocol   string
	Flag       string
	FlagPrefix string
	MemoryMB   int
	CPUs       float64
}

type SingleConfig struct {
	Common
	Image string
	Port  int
}

type MultiConfig struct {
	Common
	Services []Service
}

var nameRe = regexp.MustCompile(`^[a-z0-9-]+$`)

func parseCommon(a map[string]string) (Common, error) {
	c := Common{Protocol: "http", FlagPrefix: "CTF", MemoryMB: 256, CPUs: 0.5, Flag: a["flag"]}
	if c.Flag == "" {
		return c, fmt.Errorf("additional: missing required key %q", "flag")
	}
	if v := a["protocol"]; v != "" {
		if v != "http" && v != "tcp" {
			return c, fmt.Errorf("additional: protocol must be http or tcp, got %q", v)
		}
		c.Protocol = v
	}
	if v := a["flag_prefix"]; v != "" {
		c.FlagPrefix = v
	}
	if v := a["memory"]; v != "" {
		mb, err := parseMemory(v)
		if err != nil {
			return c, err
		}
		c.MemoryMB = mb
	}
	if v := a["cpus"]; v != "" {
		f, err := strconv.ParseFloat(v, 64)
		if err != nil || f <= 0 {
			return c, fmt.Errorf("additional: invalid cpus %q", v)
		}
		c.CPUs = f
	}
	return c, nil
}

func parseMemory(s string) (int, error) {
	s = strings.ToLower(s)
	mult := 0
	switch {
	case strings.HasSuffix(s, "m"):
		mult = 1
	case strings.HasSuffix(s, "g"):
		mult = 1024
	default:
		return 0, fmt.Errorf("additional: invalid memory %q (use e.g. 256m, 1g)", s)
	}
	n, err := strconv.Atoi(s[:len(s)-1])
	if err != nil || n <= 0 {
		return 0, fmt.Errorf("additional: invalid memory %q (use e.g. 256m, 1g)", s)
	}
	return n * mult, nil
}

func parsePort(s string) (int, error) {
	p, err := strconv.Atoi(s)
	if err != nil || p < 1 || p > 65535 {
		return 0, fmt.Errorf("additional: invalid port %q (1-65535)", s)
	}
	return p, nil
}

func ParseSingle(a map[string]string) (SingleConfig, error) {
	c := SingleConfig{Port: 80, Image: a["image"]}
	if c.Image == "" {
		return c, fmt.Errorf("additional: missing required key %q", "image")
	}
	var err error
	if c.Common, err = parseCommon(a); err != nil {
		return c, err
	}
	if v := a["port"]; v != "" {
		if c.Port, err = parsePort(v); err != nil {
			return c, err
		}
	}
	return c, nil
}

func ParseMulti(a map[string]string) (MultiConfig, error) {
	var c MultiConfig
	var err error
	if c.Common, err = parseCommon(a); err != nil {
		return c, err
	}
	raw := a["services"]
	if raw == "" {
		return c, fmt.Errorf("additional: missing required key %q", "services")
	}
	if err := json.Unmarshal([]byte(raw), &c.Services); err != nil {
		return c, fmt.Errorf("additional: services is not valid JSON: %w", err)
	}
	seen := map[string]bool{}
	entries := 0
	for _, s := range c.Services {
		if !nameRe.MatchString(s.Name) {
			return c, fmt.Errorf("services: invalid name %q (must match %s)", s.Name, nameRe)
		}
		if seen[s.Name] {
			return c, fmt.Errorf("services: duplicate name %q", s.Name)
		}
		seen[s.Name] = true
		if s.Image == "" {
			return c, fmt.Errorf("services: %q has no image", s.Name)
		}
		if s.Entry {
			entries++
			if s.Port < 1 || s.Port > 65535 {
				return c, fmt.Errorf("services: entry %q needs a port (1-65535)", s.Name)
			}
		}
	}
	if entries != 1 {
		return c, fmt.Errorf("services: exactly one entry service required, got %d", entries)
	}
	return c, nil
}
