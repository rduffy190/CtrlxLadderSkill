// A rung that mixes assignments and coils does not paint in the LD editor ("Non-toplevel demux may not have source").
// The compiler splits it into several networks that repeat the conditions: boxes first, then coils.
FUNCTION_BLOCK FB_SplitOutputs
VAR_INPUT
    bGo     : BOOL;
    bNoDeps : BOOL;
END_VAR
VAR_OUTPUT
    iA      : INT;
    iB      : INT;
    iC      : INT;
    iD      : INT;
    bX      : BOOL;
    bY      : BOOL;
    bCount  : BOOL;
    udiN    : UDINT;
END_VAR
VAR
    _bFlag  : BOOL;
END_VAR

NETWORK Five boxes and two coils (becomes 2 networks)
    bGo -> iA := 1, iB := 2, iC := 3, iD := 4, bX, S:bY

NETWORK Three MOVEs stay in one rung
    bGo -> iA := 5, iB := 6, iC := 7

NETWORK One box and one coil (mixed kinds: split)
    bGo /bCount -> udiN := ADD(udiN, 1), S:bCount
END_FUNCTION_BLOCK
