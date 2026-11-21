package scenario

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestBuildFlagFormat(t *testing.T) {
	f := BuildFlag("0123456789abcdef", Common{Flag: "php_strcmp", FlagPrefix: "CTF"})
	assert.Regexp(t, `^CTF\{.+\}$`, f)
}

func TestBuildFlagDiffersByIdentity(t *testing.T) {
	c := Common{Flag: "php_strcmp", FlagPrefix: "CTF"}
	assert.NotEqual(t, BuildFlag("0123456789abcdef", c), BuildFlag("fedcba9876543210", c))
}

func TestBuildFlagDeterministic(t *testing.T) {
	c := Common{Flag: "php_strcmp", FlagPrefix: "CTF"}
	assert.Equal(t, BuildFlag("0123456789abcdef", c), BuildFlag("0123456789abcdef", c))
}
