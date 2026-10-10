// Ladder text of references/exports/ctrlx_other_operators.xml (a ctrlX PLC Engineering export):
// SEL, MUX, LIMIT and a <type>_TO_<type> conversion. tests/run.sh checks the LD body is
// element-for-element identical to the export. (The export mixes In1/in1: CODESYS is case-insensitive.)
PROGRAM OtherOperators
VAR
    bChoice : BOOL;
    In1 : INT;
    In2 : INT;
    out1 : INT;
    iMuxSel : INT;
    in3 : INT;
    in4 : INT;
    in5 : INT;
    out2 : INT;
    minVal : INT;
    maxVal : INT;
    out3 : INT;
    out4 : REAL;
END_VAR

NETWORK Select
    -> out1 := SEL(bChoice, In1, In2)
NETWORK
    -> out2 := MUX(iMuxSel, in1, in2, in3, in4, in5)
NETWORK
    -> out3 := LIMIT(minVal, in3, maxVal)
NETWORK
    -> out4 := INT_TO_REAL(in3)
END_PROGRAM
