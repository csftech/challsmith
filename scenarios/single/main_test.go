package main

import (
	"strings"
	"sync"
	"testing"

	sdk "github.com/ctfer-io/chall-manager/sdk"
	"github.com/pulumi/pulumi/sdk/v3/go/common/resource"
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/csftech/challsmith/scenarios/internal/scenario"
)

const identity = "0123456789abcdef"

type mocks struct {
	mu   sync.Mutex
	recs []rec
}
type rec struct {
	typ string
	in  resource.PropertyMap
}

func (m *mocks) NewResource(a pulumi.MockResourceArgs) (string, resource.PropertyMap, error) {
	m.mu.Lock()
	m.recs = append(m.recs, rec{a.TypeToken, a.Inputs})
	m.mu.Unlock()
	out := a.Inputs.Copy()
	if a.TypeToken == "docker:index/container:Container" {
		out["ports"] = resource.NewArrayProperty([]resource.PropertyValue{
			resource.NewObjectProperty(resource.PropertyMap{
				"internal": resource.NewNumberProperty(80),
				"ip":       resource.NewStringProperty("127.0.0.1"),
				"external": resource.NewNumberProperty(32768),
			}),
		})
	}
	return a.Name + "_id", out, nil
}
func (m *mocks) Call(pulumi.MockCallArgs) (resource.PropertyMap, error) { return nil, nil }

func run(t *testing.T, add map[string]string) (*mocks, string, []string, error) {
	m := &mocks{}
	var conn string
	var flags []string
	err := pulumi.RunErr(func(ctx *pulumi.Context) error {
		resp := &sdk.Response{}
		if err := deploy(&sdk.Request{Ctx: ctx, Config: &sdk.Configuration{Identity: identity, Additional: add}}, resp); err != nil {
			return err
		}
		resp.ConnectionInfo.ApplyT(func(s string) string { conn = s; return s })
		resp.Flags.ApplyT(func(s []string) []string { flags = s; return s })
		return nil
	}, pulumi.WithMocks("project", "stack", m))
	return m, conn, flags, err
}

func base() map[string]string {
	return map[string]string{"image": "localhost:5000/x:1", "flag": "secret"}
}

func containers(m *mocks) []rec {
	var out []rec
	for _, r := range m.recs {
		if r.typ == "docker:index/container:Container" {
			out = append(out, r)
		}
	}
	return out
}

func TestSingleCreatesLockedDownContainer(t *testing.T) {
	m, _, _, err := run(t, base())
	require.NoError(t, err)
	cs := containers(m)
	require.Len(t, cs, 1)
	in := cs[0].in
	port := in["ports"].ArrayValue()[0].ObjectValue()
	assert.Equal(t, "127.0.0.1", port["ip"].StringValue())
	assert.Equal(t, 80.0, port["internal"].NumberValue())
	found := false
	for _, e := range in["envs"].ArrayValue() {
		found = found || strings.HasPrefix(e.StringValue(), "FLAG=CTF{")
	}
	assert.True(t, found)
	assert.Equal(t, 256.0, in["memory"].NumberValue())
	assert.Equal(t, "0.5", in["cpus"].StringValue())
	assert.Equal(t, "unless-stopped", in["restart"].StringValue())
	assert.Equal(t, "challenge-"+identity, in["name"].StringValue())
}

func TestSingleOutputsFlagAndConnectionInfo(t *testing.T) {
	_, conn, flags, err := run(t, base())
	require.NoError(t, err)
	cfg, _ := scenario.ParseSingle(base())
	want := scenario.BuildFlag(identity, cfg.Common)
	require.Equal(t, []string{want}, flags)
	assert.Contains(t, scenario.ContainerEnv(nil, want), "FLAG="+want)
	assert.Equal(t, "http://localhost:32768", conn)
}

func TestSingleTCP(t *testing.T) {
	a := base()
	a["protocol"] = "tcp"
	_, conn, _, err := run(t, a)
	require.NoError(t, err)
	assert.Equal(t, "nc localhost 32768", conn)
}

func TestSingleInvalidConfigFails(t *testing.T) {
	m, _, _, err := run(t, map[string]string{"image": "x"})
	require.Error(t, err)
	assert.Empty(t, m.recs)
}

func TestSingleBlanksProxyEnv(t *testing.T) {
	m, _, flags, err := run(t, base())
	require.NoError(t, err)
	var got []string
	for _, e := range containers(m)[0].in["envs"].ArrayValue() {
		got = append(got, e.StringValue())
	}
	assert.Equal(t, scenario.ContainerEnv(nil, flags[0]), got)
	for _, k := range []string{"HTTP_PROXY=", "HTTPS_PROXY=", "NO_PROXY=", "ALL_PROXY=", "http_proxy=", "https_proxy=", "no_proxy=", "all_proxy="} {
		assert.Contains(t, got, k)
	}
}
