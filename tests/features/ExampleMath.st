// Ladder text of references/exports/ctrlx_math_compare.xml (a ctrlX PLC Engineering export).
// tests/run.sh builds it and checks the LD body is element-for-element identical to the export.
PROGRAM ExampleMath
VAR
    in1 : INT;
    in2 : INT;
    out1 : INT;
    out2 : INT;
    out3 : INT;
    out4 : INT;
    equal : BOOL;
    neq : BOOL;
    lessthan : BOOL;
    lessthanorequal : BOOL;
    GreaterThan : BOOL;
    GraterThanOrEqual : BOOL;
END_VAR

NETWORK Addition
    -> out1 := ADD(in1, in2)
NETWORK Subtraction
    -> out2 := SUB(in1, in2)
NETWORK Multiplication
    -> out3 := MUL(in1, in2)
NETWORK Devision
    -> out4 := DIV(in1, in2)
NETWORK Equate
    [out1 = out2] -> equal
NETWORK Not Equal
    [out1 <> out2] -> neq
NETWORK Less Than
    [out1 < out2] -> LessThan
NETWORK Less Than Or Equal TO
    [out1 <= out2] -> LessThanOrEqual
NETWORK Grater Than
    [out1 > out2] -> GreaterThan
NETWORK
    [out1 >= out2] -> GraterThanOrEqual
END_PROGRAM
