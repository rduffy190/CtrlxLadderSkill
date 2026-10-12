// Library function declarations for ladder calls: pass with --lib, never as a source file
// (the converter reads their pins and doesn't put them in the project).
// ML_ command functions take their Data struct as VAR_IN_OUT (ctrlX export: ML_AxsPowerData[REF])
// and return BOOL (TRUE: command accepted). Add others from references/motion/ in the same shape.

FUNCTION ML_AxsPower : BOOL
VAR_IN_OUT
    Data : ML_AxsPowerData;
END_VAR
END_FUNCTION
