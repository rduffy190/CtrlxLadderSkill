// A parallel group after a contact fails to paint in the LD editor ("Non-toplevel demux may not have source").
// The compiler moves it to the front of the rung (same logic) and warns about the cases it cannot move.
FUNCTION_BLOCK FB_GroupFirst
VAR_INPUT
    bEnable : BOOL;
    bA      : BOOL;
    bB      : BOOL;
    bC      : BOOL;
END_VAR
VAR_OUTPUT
    bOut    : BOOL;
    iVal    : INT;
END_VAR

NETWORK Group after a contact feeding a MOVE
    bEnable (bA | bB) -> iVal := 7

NETWORK Group after a contact feeding a coil
    bEnable bC (bA | bB) -> bOut
END_FUNCTION_BLOCK
