package scenario

import "sort"

var proxyKeys = []string{"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "no_proxy", "all_proxy"}

// ContainerEnv builds the sorted KEY=value env of a challenge container. Proxy keys are
// forced empty (they must never reach a challenge, even from the image ENV) and FLAG is set last.
func ContainerEnv(svc map[string]string, flag string) []string {
	env := map[string]string{}
	for k, v := range svc {
		env[k] = v
	}
	for _, k := range proxyKeys {
		env[k] = ""
	}
	env["FLAG"] = flag
	out := make([]string, 0, len(env))
	for k, v := range env {
		out = append(out, k+"="+v)
	}
	sort.Strings(out)
	return out
}
