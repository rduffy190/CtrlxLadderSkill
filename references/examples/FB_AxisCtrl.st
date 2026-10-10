// FB_AxisCtrl in ladder, from the PressSystem project. Verified 2026-10-10: imported, compiled and run in
// ctrlX PLC Engineering 4.6 on ctrlX COREvirtual axes as part of the press system. Also scan-tested in
// ld_sim with fake MC_ models (press_tests/test_axisctrl.py).
// FB_AxisCtrl: one ctrlX axis through CXA_PLCopen: power, absolute move, halt, reset and status.
// Latches the first error with its ctrlX diagnosis until reset. Not a sequence; the caller drives it.
FUNCTION_BLOCK FB_AxisCtrl
VAR_INPUT
    bPower          : BOOL;         // power on (level)
    bMove           : BOOL;         // absolute move (Execute): needs a FALSE->TRUE edge per move
    lrPosition      : LREAL;        // absolute target, taken at the edge of bMove
    stDyn           : ST_Dynamics;  // move dynamics, taken at the edge of bMove
    bHalt           : BOOL;         // halt (Execute, level)
    lrHaltDec       : LREAL;        // halt deceleration
    bReset          : BOOL;         // reset latched error and drive ErrorStop (level)
END_VAR
VAR_OUTPUT
    bPowered        : BOOL;         // power on and confirmed
    bStandstill     : BOOL;         // powered, not moving, no error
    bInPos          : BOOL;         // current move done (held while bMove is TRUE)
    bHalted         : BOOL;         // halt done (held while bHalt is TRUE)
    bError          : BOOL;         // latched error (FB error or axis ErrorStop)
    lrActPos        : LREAL;        // actual position (valid while powered)
    eErrorID        : ERROR_CODE;   // latched error class
    dwDiagMain      : DWORD;        // latched ctrlX main diagnosis (0 for a drive ErrorStop: see ctrlX diagnostics)
    dwDiagDetail    : DWORD;        // latched ctrlX detail diagnosis
END_VAR
VAR_IN_OUT
    stAxis          : AXIS_REF;     // axis to control
END_VAR
VAR
    _bError         : BOOL;
    _eErrorID       : ERROR_CODE;
    _dwDiagMain     : DWORD;
    _dwDiagDetail   : DWORD;
    _bPowerEnable   : BOOL;         // MC_Power.Enable
    _bStatusEnable  : BOOL;         // MC_ReadStatus.Enable
    _bActPosEnable  : BOOL;         // MC_ReadActualPosition.Enable
    _bResetExecute  : BOOL;         // MC_Reset.Execute
    _bMoveExecute   : BOOL;         // MC_MoveAbsolute.Execute
    _bHaltExecute   : BOOL;         // MC_Halt.Execute
    _fbPower        : MC_Power;
    _fbReset        : MC_Reset;
    _fbStatus       : MC_ReadStatus;
    _fbActPos       : MC_ReadActualPosition;
    _fbMove         : MC_MoveAbsolute;
    _fbHalt         : MC_Halt;
END_VAR

// ===== Error latch: sub-FB results are from the previous scan, the same as a timer's Q =====
NETWORK Clear error
// Reset clears the latch once the drive has left ErrorStop
    _bError bReset /_fbStatus.ErrorStop /_fbReset.Active
        -> R:_bError, _eErrorID := ERROR_CODE.NONE_ERROR, _dwDiagMain := 0, _dwDiagDetail := 0

NETWORK Latch MC_Power error
// Each latch rung sets _bError, which locks out the rungs below: the first error is kept
    /_bError _fbPower.Error
        -> S:_bError, _eErrorID := _fbPower.ErrorID,
           _dwDiagMain := _fbPower.ErrorIdent.Additional1, _dwDiagDetail := _fbPower.ErrorIdent.Additional2

NETWORK Latch MC_MoveAbsolute error
    /_bError _fbMove.Error
        -> S:_bError, _eErrorID := _fbMove.ErrorID,
           _dwDiagMain := _fbMove.ErrorIdent.Additional1, _dwDiagDetail := _fbMove.ErrorIdent.Additional2

NETWORK Latch MC_Halt error
    /_bError _fbHalt.Error
        -> S:_bError, _eErrorID := _fbHalt.ErrorID,
           _dwDiagMain := _fbHalt.ErrorIdent.Additional1, _dwDiagDetail := _fbHalt.ErrorIdent.Additional2

NETWORK Latch MC_Reset error
    /_bError _fbReset.Error
        -> S:_bError, _eErrorID := _fbReset.ErrorID,
           _dwDiagMain := _fbReset.ErrorIdent.Additional1, _dwDiagDetail := _fbReset.ErrorIdent.Additional2

NETWORK Latch MC_ReadStatus error
    /_bError _fbStatus.Error
        -> S:_bError, _eErrorID := _fbStatus.ErrorID,
           _dwDiagMain := _fbStatus.ErrorIdent.Additional1, _dwDiagDetail := _fbStatus.ErrorIdent.Additional2

NETWORK Latch axis ErrorStop
// Error raised in the drive/motion kernel while moving; the detail is in the ctrlX diagnostics log
    /_bError _fbStatus.Valid _fbStatus.ErrorStop
        -> S:_bError, _eErrorID := ERROR_CODE.DEVICE_ERROR, _dwDiagMain := 0, _dwDiagDetail := 0

// ===== FB inputs =====
NETWORK MC_Power enable
// A failed Power (e.g. motion not RUNNING yet) needs a new edge: reset drops Enable for one scan
    bPower (/_fbPower.Error | /bReset) -> _bPowerEnable

NETWORK MC_ReadStatus enable
// Read only while powered, so a switched-off system doesn't fault at boot
    bPower (/_fbStatus.Error | /bReset) -> _bStatusEnable

NETWORK MC_ReadActualPosition enable
    bPower (/_fbActPos.Error | /bReset) -> _bActPosEnable

NETWORK MC_Reset execute
    bReset _fbStatus.ErrorStop -> _bResetExecute

NETWORK MC_MoveAbsolute execute
    bMove /_bError -> _bMoveExecute

NETWORK MC_Halt execute
// No halt on an unpowered axis or one in ErrorStop: the drive has already stopped it
    bHalt _fbPower.Status /_fbStatus.ErrorStop -> _bHaltExecute

// ===== Sub-FBs, every scan =====
NETWORK Power
    -> _fbPower(Enable := _bPowerEnable, Axis := stAxis)

NETWORK Read status
    -> _fbStatus(Enable := _bStatusEnable, Axis := stAxis)

NETWORK Read actual position
    -> _fbActPos(Enable := _bActPosEnable, Axis := stAxis)

NETWORK Reset
    -> _fbReset(Execute := _bResetExecute, Axis := stAxis)

NETWORK Move absolute
    -> _fbMove(Execute := _bMoveExecute, Position := lrPosition, Velocity := stDyn.lrVel,
               Acceleration := stDyn.lrAcc, Deceleration := stDyn.lrDec, Jerk := stDyn.lrJerk,
               BufferMode := MC_BUFFER_MODE.mcAborting, Axis := stAxis)

NETWORK Halt
// Axis pin is 'Axis' (verified on ctrlX; the manual's interface table misnames it 'Axes')
    -> _fbHalt(Execute := _bHaltExecute, Deceleration := lrHaltDec, Jerk := 0.0, Axis := stAxis)

// ===== Outputs, last =====
NETWORK Out bPowered
    _fbPower.Status -> bPowered

NETWORK Out bStandstill
    _fbStatus.Valid _fbStatus.Standstill -> bStandstill

NETWORK Out bInPos
// Gated by the command so a Done can never outlive the step that asked for it
    _fbMove.Done bMove -> bInPos

NETWORK Out bHalted
    _fbHalt.Done bHalt -> bHalted

NETWORK Out bError
    _bError -> bError

NETWORK Out copies
    -> lrActPos := _fbActPos.Position, eErrorID := _eErrorID,
       dwDiagMain := _dwDiagMain, dwDiagDetail := _dwDiagDetail
END_FUNCTION_BLOCK
