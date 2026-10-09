{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_CycleState :
(
    Idle := 0,
    Clamping,
    Working,
    Unclamping,
    Done,
    Aborting,
    Faulted
) UINT;
END_TYPE
