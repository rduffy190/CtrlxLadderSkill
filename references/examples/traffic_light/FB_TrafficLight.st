// FB_TrafficLight: two-lane traffic light. Green rests on a lane until a car waits in the
// other lane or a pedestrian asks, then yellow and an all-red clearance before the other
// lane's green. Every green lasts at least GREEN_MIN_TIME. See DESIGN.md.
// Ladder sequence: transitions -> commit -> state decode -> on change -> cyclic (no jumps:
// no fault inputs). After the decode, the logic uses contacts on the state BOOLs, never
// compares in parallel.
FUNCTION_BLOCK FB_TrafficLight
VAR_INPUT
    bCarA           : BOOL;     // car present in lane A
    bCarB           : BOOL;     // car present in lane B
    bPedButton      : BOOL;     // pedestrian button (momentary); latched internally
END_VAR
VAR_OUTPUT
    eState          : E_TrafficState;   // current step, for HMI / online view
    bRedA           : BOOL;     // lane A red
    bYellowA        : BOOL;     // lane A yellow
    bGreenA         : BOOL;     // lane A green
    bRedB           : BOOL;     // lane B red
    bYellowB        : BOOL;     // lane B yellow
    bGreenB         : BOOL;     // lane B green
END_VAR
VAR
    _eState         : E_TrafficState;   // the state; eState is only a copy for the caller
    _eNextState     : E_TrafficState;   // written by transitions, committed to _eState
    _eLastState     : E_TrafficState;
    _bStateChanged  : BOOL;             // TRUE on the scan the state changed
    _bPedRequest    : BOOL;             // stored pedestrian request, cleared when a green starts
    _bStAllRedToA   : BOOL;             // state decoded after the commit: one BOOL per state
    _bStGreenA      : BOOL;
    _bStYellowA     : BOOL;
    _bStAllRedToB   : BOOL;
    _bStGreenB      : BOOL;
    _bStYellowB     : BOOL;
    _tStepTime      : TIME := ALL_RED_TIME; // time of the current step; starts as AllRedToA's
    _fbStepTimer    : TON;
END_VAR
VAR CONSTANT
    GREEN_MIN_TIME  : TIME := T#30S;
    YELLOW_TIME     : TIME := T#6S;
    ALL_RED_TIME    : TIME := T#2S;
END_VAR

// ===== Inputs =====
NETWORK Ped request
// One press is enough: held until the next green starts
    bPedButton -> S:_bPedRequest

// ===== 2. Transitions only =====
NETWORK T AllRedToA -> GreenA
    [_eState = E_TrafficState.AllRedToA] _fbStepTimer.Q -> _eNextState := E_TrafficState.GreenA

NETWORK T GreenA -> YellowA
// Only after the minimum green, and only on demand from lane B or a pedestrian
    [_eState = E_TrafficState.GreenA] _fbStepTimer.Q (bCarB | _bPedRequest)
        -> _eNextState := E_TrafficState.YellowA

NETWORK T YellowA -> AllRedToB
    [_eState = E_TrafficState.YellowA] _fbStepTimer.Q -> _eNextState := E_TrafficState.AllRedToB

NETWORK T AllRedToB -> GreenB
    [_eState = E_TrafficState.AllRedToB] _fbStepTimer.Q -> _eNextState := E_TrafficState.GreenB

NETWORK T GreenB -> YellowB
// Only after the minimum green, and only on demand from lane A or a pedestrian
    [_eState = E_TrafficState.GreenB] _fbStepTimer.Q (bCarA | _bPedRequest)
        -> _eNextState := E_TrafficState.YellowB

NETWORK T YellowB -> AllRedToA
    [_eState = E_TrafficState.YellowB] _fbStepTimer.Q -> _eNextState := E_TrafficState.AllRedToA

NETWORK T Invalid state -> AllRedToA
// The CASE ELSE: an unknown value (e.g. after an online change) restarts from all red
    [_eState > E_TrafficState.YellowB] -> _eNextState := E_TrafficState.AllRedToA

NETWORK Commit transitions
    -> _eState := _eNextState

// ===== State decode: one compare per rung, so later rungs use contacts =====
NETWORK Decode AllRedToA
    [_eState = E_TrafficState.AllRedToA] -> _bStAllRedToA

NETWORK Decode GreenA
    [_eState = E_TrafficState.GreenA] -> _bStGreenA

NETWORK Decode YellowA
    [_eState = E_TrafficState.YellowA] -> _bStYellowA

NETWORK Decode AllRedToB
    [_eState = E_TrafficState.AllRedToB] -> _bStAllRedToB

NETWORK Decode GreenB
    [_eState = E_TrafficState.GreenB] -> _bStGreenB

NETWORK Decode YellowB
    [_eState = E_TrafficState.YellowB] -> _bStYellowB

// ===== 3. On change: entry actions of the new state =====
NETWORK State changed
    [_eState <> _eLastState] -> _bStateChanged

NETWORK Entry all-red
    _bStateChanged (_bStAllRedToA | _bStAllRedToB) -> _tStepTime := ALL_RED_TIME

NETWORK Entry green
// The change the pedestrian waited for has happened, so the request is served
    _bStateChanged (_bStGreenA | _bStGreenB) -> _tStepTime := GREEN_MIN_TIME, R:_bPedRequest

NETWORK Entry yellow
    _bStateChanged (_bStYellowA | _bStYellowB) -> _tStepTime := YELLOW_TIME

NETWORK Remember state
    -> _eLastState := _eState

// ===== 4. Cyclic: sub-FB calls, then outputs last =====
NETWORK Step timer
// Off for the change scan, so it restarts in every new step
    /_bStateChanged _fbStepTimer(PT := _tStepTime)

NETWORK Out bRedA
    (_bStAllRedToA | _bStAllRedToB | _bStGreenB | _bStYellowB) -> bRedA

NETWORK Out bYellowA
    _bStYellowA -> bYellowA

NETWORK Out bGreenA
    _bStGreenA -> bGreenA

NETWORK Out bRedB
    (_bStAllRedToA | _bStGreenA | _bStYellowA | _bStAllRedToB) -> bRedB

NETWORK Out bYellowB
    _bStYellowB -> bYellowB

NETWORK Out bGreenB
    _bStGreenB -> bGreenB

NETWORK Out copies
    -> eState := _eState
END_FUNCTION_BLOCK
