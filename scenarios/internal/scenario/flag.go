package scenario

import "github.com/ctfer-io/chall-manager/sdk"

// BuildFlag returns "<prefix>{<variated>}", unique per identity.
func BuildFlag(identity string, c Common) string {
	return c.FlagPrefix + "{" + sdk.Variate(identity, c.Flag) + "}"
}
