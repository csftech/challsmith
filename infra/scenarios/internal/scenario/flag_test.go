package scenario

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestBuildFlagFormat(t *testing.T) {
	f := BuildFlag("3f9a1c07e2b84d65", Common{Flag: "php_strcmp_array", FlagPrefix: "APS"})
	assert.Equal(t, "APS{php_strcmp_array_3f9a1c07e2b84d65}", f)
}

func TestBuildFlagDiffersByIdentity(t *testing.T) {
	c := Common{Flag: "php_strcmp", FlagPrefix: "APS"}
	assert.NotEqual(t, BuildFlag("0123456789abcdef", c), BuildFlag("fedcba9876543210", c))
}

// A short template must not shrink the flag space: only the identity makes flags distinct.
func TestBuildFlagShortTemplateStillUnique(t *testing.T) {
	c := Common{Flag: "ok", FlagPrefix: "APS"}
	seen := map[string]bool{}
	for _, id := range []string{"0000000000000001", "0000000000000002", "1000000000000000", "ffffffffffffffff"} {
		f := BuildFlag(id, c)
		assert.False(t, seen[f], "collision for %s", id)
		seen[f] = true
	}
}

func TestBuildFlagDeterministic(t *testing.T) {
	c := Common{Flag: "php_strcmp", FlagPrefix: "APS"}
	assert.Equal(t, BuildFlag("0123456789abcdef", c), BuildFlag("0123456789abcdef", c))
}
