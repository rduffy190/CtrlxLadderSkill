FUNCTION_BLOCK FB_Valve
VAR_INPUT
    rSetpoint : REAL;   // setpoint
    bOpen : BOOL;       // command open
END_VAR
VAR_OUTPUT
    eState : INT;       // state
    bOpened : BOOL;     // feedback reached
END_VAR
    eState := 0;
    bOpened := bOpen;
END_FUNCTION_BLOCK
