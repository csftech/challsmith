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

	"github.com/csftech/challsmith/infra/scenarios/internal/scenario"
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
		// exported so RunErr waits for the applies before returning
		ctx.Export("conn", resp.ConnectionInfo.ApplyT(func(s string) string { conn = s; return s }))
		ctx.Export("flags", resp.Flags.ApplyT(func(s []string) []string { flags = s; return s }))
		return nil
	}, pulumi.WithMocks("project", "stack", m))
	return m, conn, flags, err
}

const svcs = `[{"name":"web","image":"w:1","port":80,"entry":true},{"name":"php","image":"p:1","env":{"A":"b"}},{"name":"db","image":"d:1","env":{"MYSQL_PASSWORD":"pw"}}]`

func base() map[string]string {
	return map[string]string{"flag": "secret", "services": svcs}
}

func ofType(m *mocks, typ string) []rec {
	var out []rec
	for _, r := range m.recs {
		if r.typ == typ {
			out = append(out, r)
		}
	}
	return out
}

func containers(m *mocks) []rec { return ofType(m, "docker:index/container:Container") }

func envs(r rec) []string {
	var out []string
	for _, e := range r.in["envs"].ArrayValue() {
		out = append(out, e.StringValue())
	}
	return out
}

func TestMultiOneNetworkAllAttached(t *testing.T) {
	m, _, _, err := run(t, base())
	require.NoError(t, err)
	nets := ofType(m, "docker:index/network:Network")
	require.Len(t, nets, 1)
	assert.Equal(t, "challenge-"+identity, nets[0].in["name"].StringValue())
	assert.False(t, nets[0].in["internal"].BoolValue())
	cs := containers(m)
	require.Len(t, cs, 3)
	for _, c := range cs {
		na := c.in["networksAdvanced"].ArrayValue()
		require.Len(t, na, 1)
		o := na[0].ObjectValue()
		assert.Equal(t, "challenge-"+identity, o["name"].StringValue())
		name := strings.TrimPrefix(c.in["name"].StringValue(), "challenge-"+identity+"-")
		require.Len(t, o["aliases"].ArrayValue(), 1)
		assert.Equal(t, name, o["aliases"].ArrayValue()[0].StringValue())
		assert.Equal(t, 256.0, c.in["memory"].NumberValue())
		assert.Equal(t, "0.5", c.in["cpus"].StringValue())
		assert.Equal(t, "unless-stopped", c.in["restart"].StringValue())
	}
}

func TestMultiOnlyEntryPublishes(t *testing.T) {
	m, _, _, err := run(t, base())
	require.NoError(t, err)
	for _, c := range containers(m) {
		var ports []resource.PropertyValue
		if c.in["ports"].IsArray() {
			ports = c.in["ports"].ArrayValue()
		}
		if c.in["name"].StringValue() == "challenge-"+identity+"-web" {
			require.Len(t, ports, 1)
			assert.Equal(t, "127.0.0.1", ports[0].ObjectValue()["ip"].StringValue())
			assert.Equal(t, 80.0, ports[0].ObjectValue()["internal"].NumberValue())
		} else {
			assert.Empty(t, ports)
		}
	}
}

func TestMultiFlagInAllContainers(t *testing.T) {
	m, _, flags, err := run(t, base())
	require.NoError(t, err)
	require.Len(t, flags, 1)
	for _, c := range containers(m) {
		assert.Contains(t, envs(c), "FLAG="+flags[0])
	}
	for _, c := range containers(m) {
		if strings.HasSuffix(c.in["name"].StringValue(), "-db") {
			assert.Contains(t, envs(c), "MYSQL_PASSWORD=pw")
		}
	}
}

func TestMultiServiceEnvCannotOverrideFlag(t *testing.T) {
	a := base()
	a["services"] = `[{"name":"web","image":"w:1","port":80,"entry":true,"env":{"FLAG":"x"}}]`
	m, _, flags, err := run(t, a)
	require.NoError(t, err)
	e := envs(containers(m)[0])
	assert.Equal(t, scenario.ContainerEnv(nil, flags[0]), e)
}

func TestMultiOutputs(t *testing.T) {
	_, conn, flags, err := run(t, base())
	require.NoError(t, err)
	assert.Equal(t, "http://localhost:32768", conn)
	cfg, _ := scenario.ParseMulti(base())
	assert.Equal(t, []string{scenario.BuildFlag(identity, cfg.Common)}, flags)
}

func TestMultiInvalidConfigFails(t *testing.T) {
	m, _, _, err := run(t, map[string]string{"flag": "x"})
	require.Error(t, err)
	assert.Empty(t, m.recs)
}

func TestMultiServiceEnvCannotSetProxy(t *testing.T) {
	a := base()
	a["services"] = `[{"name":"web","image":"w:1","port":80,"entry":true,"env":{"HTTP_PROXY":"http://x:1","http_proxy":"http://x:1"}}]`
	m, _, _, err := run(t, a)
	require.NoError(t, err)
	e := envs(containers(m)[0])
	assert.Contains(t, e, "HTTP_PROXY=")
	assert.Contains(t, e, "http_proxy=")
	for _, k := range []string{"HTTPS_PROXY=", "NO_PROXY=", "ALL_PROXY=", "https_proxy=", "no_proxy=", "all_proxy="} {
		assert.Contains(t, e, k)
	}
	assert.NotContains(t, e, "HTTP_PROXY=http://x:1")
}
