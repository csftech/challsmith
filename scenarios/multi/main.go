// Command multi deploys several Docker containers on a per-instance network.
package main

import (
	"fmt"
	"sort"
	"strconv"

	sdk "github.com/ctfer-io/chall-manager/sdk"
	"github.com/pulumi/pulumi-docker/sdk/v4/go/docker"
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi"

	"github.com/csftech/challsmith/scenarios/internal/scenario"
)

func main() { sdk.Run(deploy) }

func deploy(req *sdk.Request, resp *sdk.Response, opts ...pulumi.ResourceOption) error {
	cfg, err := scenario.ParseMulti(req.Config.Additional)
	if err != nil {
		return err
	}
	id := req.Config.Identity
	flag := scenario.BuildFlag(id, cfg.Common)

	net, err := docker.NewNetwork(req.Ctx, "network", &docker.NetworkArgs{
		Name:     pulumi.String("challenge-" + id),
		Internal: pulumi.BoolPtr(false),
	}, opts...)
	if err != nil {
		return err
	}

	var entry *docker.Container
	var entryProto string
	for _, s := range cfg.Services {
		img, err := docker.NewRemoteImage(req.Ctx, "image-"+s.Name, &docker.RemoteImageArgs{
			Name:        pulumi.String(s.Image),
			KeepLocally: pulumi.BoolPtr(true),
		}, opts...)
		if err != nil {
			return err
		}

		env := map[string]string{}
		for k, v := range s.Env {
			env[k] = v
		}
		env["FLAG"] = flag // set last: service env must not override the flag
		keys := make([]string, 0, len(env))
		for k := range env {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		envs := pulumi.StringArray{}
		for _, k := range keys {
			envs = append(envs, pulumi.String(k+"="+env[k]))
		}

		args := &docker.ContainerArgs{
			Name:    pulumi.String("challenge-" + id + "-" + s.Name),
			Image:   img.ImageId,
			Envs:    envs,
			Memory:  pulumi.Int(cfg.MemoryMB),
			Cpus:    pulumi.String(strconv.FormatFloat(cfg.CPUs, 'f', -1, 64)),
			Restart: pulumi.String("unless-stopped"),
			Rm:      pulumi.Bool(false),
			NetworksAdvanced: docker.ContainerNetworksAdvancedArray{&docker.ContainerNetworksAdvancedArgs{
				Name:    net.Name,
				Aliases: pulumi.StringArray{pulumi.String(s.Name)},
			}},
		}
		if s.Entry {
			args.Ports = docker.ContainerPortArray{&docker.ContainerPortArgs{
				Internal: pulumi.Int(s.Port),
				Ip:       pulumi.String("127.0.0.1"),
				Protocol: pulumi.String("tcp"),
			}}
		}
		c, err := docker.NewContainer(req.Ctx, "container-"+s.Name, args, opts...)
		if err != nil {
			return err
		}
		if s.Entry {
			entry, entryProto = c, cfg.Protocol
		}
	}

	resp.ConnectionInfo = entry.Ports.ApplyT(func(ports []docker.ContainerPort) (string, error) {
		if len(ports) == 0 || ports[0].External == nil {
			return "", fmt.Errorf("entry container has no published port")
		}
		return scenario.ConnectionInfo(entryProto, *ports[0].External), nil
	}).(pulumi.StringOutput)
	resp.Flags = pulumi.ToStringArray([]string{flag}).ToStringArrayOutput()
	return nil
}
