package scenario

// BuildFlag returns "<prefix>{<flag>_<identity>}".
// The identity is chall-manager's 64-bit crypto-random per-instance value, so flags stay distinct
// however short the template is; it is deterministic so re-running the scenario keeps the flag.
func BuildFlag(identity string, c Common) string {
	return c.FlagPrefix + "{" + c.Flag + "_" + identity + "}"
}
