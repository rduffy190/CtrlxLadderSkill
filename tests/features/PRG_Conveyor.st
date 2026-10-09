// Conveyor written in ladder
PROGRAM PRG_Conveyor
VAR
    bRun : BOOL;              // conveyor running
    bFault : BOOL;
    bReset : BOOL;
    bAuto, bManual, bJog : BOOL;
    fbRunOn : TON;            // run-on timer
    fbCount : CTU;
    afbValve : ARRAY[1..2] OF FB_Valve;
    rTemp : REAL;
    bHot : BOOL;              // decoded compare
    rSp, rOut : REAL;
    iCount : INT;
    tEt : TIME;
END_VAR

NETWORK Start/stop seal-in
// Stop is wired NC, so GVL_IO.bDI_StopOk is TRUE when healthy
    (GVL_IO.bDI_Start | bRun) GVL_IO.bDI_StopOk /bFault -> bRun

NETWORK Run-on delay
    bRun fbRunOn(PT := T#5S, ET => tEt) -> bManual   // trailing comment

NETWORK Count parts
    -> fbCount(CU := bJog, RESET := bReset, PV := 100, Q => bAuto, CV => iCount)

NETWORK
LABEL lblValve
    (bAuto (bJog | /bManual) | bManual N:bJog) -> bJog

NETWORK Hot
// Compares never go in parallel branches: decode first
    [rTemp > 80.0] -> bHot

NETWORK Over-temperature
    (bHot | bFault) /bReset -> S:bFault

NETWORK Setpoint copy
    bAuto -> rOut := rSp, bJog

NETWORK Global timer, unknown-type box
    bRun fbGlobalTimer(PT := T#1S) -> bJog

NETWORK Valve
    -> afbValve[1](rSetpoint := rSp, bOpen := bAuto, eState => iCount, bOpened => bReset)
    
NETWORK Skip
    bFault -> JMP:lblValve

NETWORK End
    TRUE -> RET
END_PROGRAM
