// Command single deploys one Docker container per challenge instance.
package main

import (
	"fmt"
	"strconv"

	sdk "github.com/ctfer-io/chall-manager/sdk"
	"github.com/pulumi/pulumi-docker/sdk/v5/go/docker"
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi"

	"github.com/csftech/challsmith/scenarios/internal/scenario"
)

func main() { sdk.Run(deploy) }

func deploy(req *sdk.Request, resp *sdk.Response, opts ...pulumi.ResourceOption) error {
	cfg, err := scenario.ParseSingle(req.Config.Additional)
	if err != nil {
		return err
	}
	flag := scenario.BuildFlag(req.Config.Identity, cfg.Common)

	img, err := docker.NewRemoteImage(req.Ctx, "image", &docker.RemoteImageArgs{
		Name:        pulumi.String(cfg.Image),
		KeepLocally: pulumi.BoolPtr(true),
	}, opts...)
	if err != nil {
		return err
	}

	c, err := docker.NewContainer(req.Ctx, "container", &docker.ContainerArgs{
		Name:    pulumi.String("challenge-" + req.Config.Identity),
		Image:   img.ImageId,
		Envs:    pulumi.ToStringArray(scenario.ContainerEnv(nil, flag)),
		Memory:  pulumi.Int(cfg.MemoryMB),
		Cpus:    pulumi.String(strconv.FormatFloat(cfg.CPUs, 'f', -1, 64)),
		Restart: pulumi.String("unless-stopped"),
		Rm:      pulumi.Bool(false),
		Ports: docker.ContainerPortArray{&docker.ContainerPortArgs{
			Internal: pulumi.Int(cfg.Port),
			Ip:       pulumi.String("127.0.0.1"),
			Protocol: pulumi.String("tcp"),
		}},
	}, opts...)
	if err != nil {
		return err
	}

	resp.ConnectionInfo = c.Ports.ApplyT(func(ports []docker.ContainerPort) (string, error) {
		if len(ports) == 0 || ports[0].External == nil {
			return "", fmt.Errorf("container has no published port")
		}
		return scenario.ConnectionInfo(cfg.Protocol, *ports[0].External), nil
	}).(pulumi.StringOutput)
	resp.Flags = pulumi.ToStringArray([]string{flag}).ToStringArrayOutput()
	return nil
}
