// FB_SimDecl: declaration forms the simulator must read. VAR_IN_OUT CONSTANT is a variable
// (no initial values), and based literals (16#...) are constants.
FUNCTION_BLOCK FB_SimDecl
VAR_OUTPUT
    bAbove : BOOL;      // wLevel above LIMIT
END_VAR
VAR_IN_OUT CONSTANT
    wLevel : WORD;      // read-only reference
END_VAR
VAR CONSTANT
    LIMIT : WORD := 16#00FF;
END_VAR

NETWORK Above limit
    [wLevel > LIMIT] -> bAbove
END_FUNCTION_BLOCK
