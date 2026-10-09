// FB_CycleLD: one clamp/work/unclamp cycle per Execute, with abort, step timeouts and latched faults.
// Ladder version of FB_Cycle: jumps -> commit -> transitions -> commit -> state decode -> on change
// -> FB calls -> outputs. After the decode the logic uses contacts, never compares in parallel.
FUNCTION_BLOCK FB_CycleLD
VAR_INPUT
    bExecute        : BOOL;     // run one cycle; hold TRUE until Done/Error, then remove
    bAbort          : BOOL;     // abort request (level), e.g. guard opened
    bReset          : BOOL;     // fault reset (level), only acts once Execute is removed
    bExternalFault  : BOOL;     // fault cause from outside, e.g. drive fault
    bClamped        : BOOL;     // feedback: clamp closed
    bUnclamped      : BOOL;     // feedback: clamp open
    bWorkDone       : BOOL;     // feedback: work station finished
END_VAR
VAR_OUTPUT
    eState          : E_CycleState; // current step, for HMI / online view
    bBusy           : BOOL;         // cycle in progress
    bDone           : BOOL;         // cycle finished; held until Execute is removed
    bError          : BOOL;         // faulted; held until reset with Execute removed
    uiFaultCode     : UINT;         // first fault that latched, 0 = none
    eFaultState     : E_CycleState; // step that was active when the fault latched
    bClampCmd       : BOOL;         // valve: close clamp
    bWorkCmd        : BOOL;         // start work station
END_VAR
VAR
    _eState         : E_CycleState; // the state; eState is only a copy for the caller
    _eNextState     : E_CycleState; // written by jumps/transitions, committed to _eState after each section
    _eLastState     : E_CycleState;
    _bStateChanged  : BOOL;         // TRUE on the scan the state changed (on-change section)
    _uiFaultCode    : UINT;
    _eFaultState    : E_CycleState;
    _tStepTimeout   : TIME;         // timeout of the current step, T#0S = none
    _bStIdle        : BOOL;         // state decoded after the commit: one BOOL per state
    _bStClamping    : BOOL;
    _bStWorking     : BOOL;
    _bStUnclamping  : BOOL;
    _bStDone        : BOOL;
    _bStAborting    : BOOL;
    _bStFaulted     : BOOL;
    _fbStepTimer    : TON;
END_VAR
VAR CONSTANT
    CLAMP_TIMEOUT       : TIME := T#3S;
    WORK_TIMEOUT        : TIME := T#30S;
    UNCLAMP_TIMEOUT     : TIME := T#3S;
    FAULT_NONE          : UINT := 0;
    FAULT_EXTERNAL      : UINT := 1;
    FAULT_STEP_TIMEOUT  : UINT := 2;
    FAULT_INVALID_STATE : UINT := 99;
END_VAR

// ===== 1. Jumps: highest priority first, each one locks out the ones below =====
NETWORK J1 External fault
    [_eState <> E_CycleState.Faulted] bExternalFault
        -> _eNextState := E_CycleState.Faulted, _uiFaultCode := FAULT_EXTERNAL, _eFaultState := _eState

NETWORK J2 Step timeout
// The step timer belongs to the current step, so this one rung covers every step's timeout
    [_eState <> E_CycleState.Faulted] /bExternalFault _fbStepTimer.Q
        -> _eNextState := E_CycleState.Faulted, _uiFaultCode := FAULT_STEP_TIMEOUT, _eFaultState := _eState

NETWORK J3 Abort while clamping
// One compare per rung: abort in two states is two networks (neither state is Faulted)
    [_eState = E_CycleState.Clamping] /bExternalFault /_fbStepTimer.Q bAbort
        -> _eNextState := E_CycleState.Aborting

NETWORK J4 Abort while working
    [_eState = E_CycleState.Working] /bExternalFault /_fbStepTimer.Q bAbort
        -> _eNextState := E_CycleState.Aborting

NETWORK Commit jumps
    -> _eState := _eNextState

// ===== 2. Transitions only =====
NETWORK T Idle -> Clamping
    [_eState = E_CycleState.Idle] bExecute /bAbort -> _eNextState := E_CycleState.Clamping

NETWORK T Clamping -> Working
    [_eState = E_CycleState.Clamping] bClamped -> _eNextState := E_CycleState.Working

NETWORK T Working -> Unclamping
    [_eState = E_CycleState.Working] bWorkDone -> _eNextState := E_CycleState.Unclamping

NETWORK T Unclamping -> Done
    [_eState = E_CycleState.Unclamping] bUnclamped -> _eNextState := E_CycleState.Done

NETWORK T Done -> Idle
// Hold until the command is removed: this is what replaces an edge on Execute
    [_eState = E_CycleState.Done] /bExecute -> _eNextState := E_CycleState.Idle

NETWORK T Aborting -> Idle
    [_eState = E_CycleState.Aborting] bUnclamped /bExecute -> _eNextState := E_CycleState.Idle

NETWORK T Faulted -> Idle
    [_eState = E_CycleState.Faulted] bReset /bExecute /bExternalFault -> _eNextState := E_CycleState.Idle

NETWORK T Invalid state -> Faulted
// The CASE ELSE: any value past the last state (e.g. after an online change)
    [_eState > E_CycleState.Faulted]
        -> _eNextState := E_CycleState.Faulted, _uiFaultCode := FAULT_INVALID_STATE, _eFaultState := _eState

NETWORK Commit transitions
    -> _eState := _eNextState

// ===== State decode: one compare per rung, so later rungs use contacts =====
NETWORK Decode Idle
    [_eState = E_CycleState.Idle] -> _bStIdle

NETWORK Decode Clamping
    [_eState = E_CycleState.Clamping] -> _bStClamping

NETWORK Decode Working
    [_eState = E_CycleState.Working] -> _bStWorking

NETWORK Decode Unclamping
    [_eState = E_CycleState.Unclamping] -> _bStUnclamping

NETWORK Decode Done
    [_eState = E_CycleState.Done] -> _bStDone

NETWORK Decode Aborting
    [_eState = E_CycleState.Aborting] -> _bStAborting

NETWORK Decode Faulted
    [_eState = E_CycleState.Faulted] -> _bStFaulted

// ===== 3. On change: common actions, then entry actions of the new state =====
NETWORK State changed
    [_eState <> _eLastState] -> _bStateChanged

NETWORK Common: no timeout unless the new step sets one
    _bStateChanged -> _tStepTimeout := T#0S

NETWORK Entry Idle
// Idle means no fault: fault info only exists while the sequence is out of Idle
    _bStateChanged _bStIdle -> _uiFaultCode := FAULT_NONE, _eFaultState := E_CycleState.Idle

NETWORK Entry Clamping
    _bStateChanged _bStClamping -> _tStepTimeout := CLAMP_TIMEOUT

NETWORK Entry Working
    _bStateChanged _bStWorking -> _tStepTimeout := WORK_TIMEOUT

NETWORK Entry Unclamping, Aborting
    _bStateChanged (_bStUnclamping | _bStAborting) -> _tStepTimeout := UNCLAMP_TIMEOUT

NETWORK Remember state
    -> _eLastState := _eState

// ===== 4. Cyclic: every sub-FB call, then every output last =====
NETWORK Step timer
// Off for the change scan, so it restarts in every new step
    [_tStepTimeout > T#0S] /_bStateChanged _fbStepTimer(PT := _tStepTimeout)

NETWORK Out bBusy
    (_bStClamping | _bStWorking | _bStUnclamping | _bStAborting) -> bBusy

NETWORK Out bDone
    _bStDone -> bDone

NETWORK Out bError
    _bStFaulted -> bError

NETWORK Out bClampCmd
// Aborting opens the clamp
    (_bStClamping | _bStWorking) -> bClampCmd

NETWORK Out bWorkCmd
    _bStWorking -> bWorkCmd

NETWORK Out copies
// The logic above never reads its own outputs
    -> eState := _eState, uiFaultCode := _uiFaultCode, eFaultState := _eFaultState
END_FUNCTION_BLOCK
