package scenario

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestContainerEnvBlanksProxyAndSetsFlagLast(t *testing.T) {
	got := ContainerEnv(map[string]string{"HTTP_PROXY": "x", "FLAG": "evil", "A": "1"}, "real")
	assert.Equal(t, []string{
		"A=1", "ALL_PROXY=", "FLAG=real", "HTTPS_PROXY=", "HTTP_PROXY=", "NO_PROXY=",
		"all_proxy=", "http_proxy=", "https_proxy=", "no_proxy=",
	}, got)
}
