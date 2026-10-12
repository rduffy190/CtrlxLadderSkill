// Rebuilds exports/ctrlx_function_calls.xml (ctrlX PLC Engineering 4.6.2): user and library
// function calls in ladder. The Fn_ bodies and the types of Out3/Out4 aren't in the export.
// The export leaves Out3/Out4 open ('???'), which doesn't compile: every function pin must be
// connected. Here they go to _bOut3/_bOut4, and run.sh patches the export the same way.
TYPE ST_StateClientData :
STRUCT
    iState : INT;
END_STRUCT
END_TYPE

FUNCTION Fn_UserFunc : BOOL
VAR_INPUT
    bExecute : BOOL;
END_VAR
VAR_OUTPUT
    retVal : INT;
    Out3 : BOOL;
END_VAR
Fn_UserFunc := bExecute;
retVal := 1;
END_FUNCTION

FUNCTION Fn_UserFunc2 : REAL
VAR_INPUT
    paramA : REAL;
    paramB : REAL;
END_VAR
VAR_OUTPUT
    structVal : ST_StateClientData;
    Out4 : BOOL;
END_VAR
Fn_UserFunc2 := paramA + paramB;
END_FUNCTION

PROGRAM ExFunCalls
VAR
    _bExecute : BOOL;
    _bExDone : BOOL;
    _iRetVal : INT;
    _rRetVal : REAL;
    _stStuctVal : ST_StateClientData;
    _rParamVal : REAL;
    _stParams : ML_AxsPowerData;
    _bExecuteOK : BOOL;
    _bOut3 : BOOL;
    _bOut4 : BOOL;
END_VAR

NETWORK
    _bExecute Fn_UserFunc(retVal => _iRetVal, Out3 => _bOut3) -> _bExDone

NETWORK
    _bExecute _rRetVal := Fn_UserFunc2(paramA := 1.0, paramB := _rParamVal, structVal => _stStuctVal, Out4 => _bOut4) -> _bExDone

NETWORK
    _bExecute _bExecuteOK := ML_AxsPower(Data := _stParams) -> _bExDone
END_PROGRAM
