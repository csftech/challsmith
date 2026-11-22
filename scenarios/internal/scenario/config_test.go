package scenario

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestParseSingleDefaults(t *testing.T) {
	c, err := ParseSingle(map[string]string{"image": "localhost:5000/x:1", "flag": "abc"})
	require.NoError(t, err)
	assert.Equal(t, 80, c.Port)
	assert.Equal(t, "http", c.Protocol)
	assert.Equal(t, "APS", c.FlagPrefix)
	assert.Equal(t, 256, c.MemoryMB)
	assert.Equal(t, 0.5, c.CPUs)
}

func TestParseSingleRequiresImageAndFlag(t *testing.T) {
	_, err := ParseSingle(map[string]string{"flag": "abc"})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "image")
	_, err = ParseSingle(map[string]string{"image": "x"})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "flag")
}

func TestParseSingleRejectsBadPort(t *testing.T) {
	for _, p := range []string{"abc", "0", "70000"} {
		_, err := ParseSingle(map[string]string{"image": "x", "flag": "f", "port": p})
		assert.Error(t, err, p)
	}
}

func TestParseSingleRejectsBadProtocol(t *testing.T) {
	_, err := ParseSingle(map[string]string{"image": "x", "flag": "f", "protocol": "udp"})
	assert.Error(t, err)
}

func TestParseMemory(t *testing.T) {
	for in, want := range map[string]int{"512m": 512, "1g": 1024} {
		c, err := ParseSingle(map[string]string{"image": "x", "flag": "f", "memory": in})
		require.NoError(t, err)
		assert.Equal(t, want, c.MemoryMB)
	}
	_, err := ParseSingle(map[string]string{"image": "x", "flag": "f", "memory": "abc"})
	assert.Error(t, err)
}

const goodServices = `[{"name":"web","image":"a","port":80,"entry":true},{"name":"db","image":"b","env":{"X":"1"}},{"name":"cache","image":"c"}]`

func multi(services string) map[string]string {
	return map[string]string{"flag": "f", "services": services}
}

func TestParseMultiEntry(t *testing.T) {
	c, err := ParseMulti(multi(goodServices))
	require.NoError(t, err)
	require.Len(t, c.Services, 3)
	assert.True(t, c.Services[0].Entry)
	assert.Equal(t, "web", c.Services[0].Name)
	assert.Equal(t, 80, c.Services[0].Port)
}

func TestParseMultiRejects(t *testing.T) {
	cases := map[string]string{
		"bad json":      `{`,
		"no entry":      `[{"name":"a","image":"x","port":80}]`,
		"two entries":   `[{"name":"a","image":"x","port":80,"entry":true},{"name":"b","image":"x","port":80,"entry":true}]`,
		"entry no port": `[{"name":"a","image":"x","entry":true}]`,
		"dup name":      `[{"name":"a","image":"x","port":80,"entry":true},{"name":"a","image":"x"}]`,
		"bad name":      `[{"name":"A_b","image":"x","port":80,"entry":true}]`,
	}
	for name, s := range cases {
		_, err := ParseMulti(multi(s))
		assert.Error(t, err, name)
	}
	_, err := ParseMulti(map[string]string{"services": goodServices})
	assert.Error(t, err)
	_, err = ParseMulti(map[string]string{"flag": "f"})
	assert.Error(t, err)
}
