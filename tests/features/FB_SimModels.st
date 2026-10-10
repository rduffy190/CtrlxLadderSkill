// Feature test for ld_sim: struct MOVE copies every member, struct members in compares,
// and an FB box run through a Python model (outputs read back as contacts and via =>).
TYPE ST_Cfg :
STRUCT
    rLimit  : REAL;
    rGain   : REAL;
END_STRUCT
END_TYPE

FUNCTION_BLOCK FB_Child
VAR_INPUT
    bRun    : BOOL;
    rIn     : REAL;
END_VAR
VAR_OUTPUT
    bBusy   : BOOL;
    rOut    : REAL;
END_VAR
bBusy := bRun;
rOut := rIn;
END_FUNCTION_BLOCK

FUNCTION_BLOCK FB_SimModels
VAR_INPUT
    stCfg   : ST_Cfg;
    rValue  : REAL;
    bLatch  : BOOL;
END_VAR
VAR_OUTPUT
    bOver   : BOOL;
    bBusy   : BOOL;
    rChild  : REAL;
END_VAR
VAR
    _stCfg  : ST_Cfg;
    _rScaled : REAL;
    _fbChild : FB_Child;
END_VAR

NETWORK Latch config
    bLatch -> _stCfg := stCfg

NETWORK Scale
    -> _rScaled := MUL(rValue, _stCfg.rGain)

NETWORK Over limit
    [_rScaled > _stCfg.rLimit] -> bOver

NETWORK Child
    -> _fbChild(bRun := bOver, rIn := _rScaled, rOut => rChild)

NETWORK Out bBusy
    _fbChild.bBusy -> bBusy
END_FUNCTION_BLOCK
