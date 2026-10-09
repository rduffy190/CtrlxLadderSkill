// PRG_Traffic: maps the traffic light I/O to FB_TrafficLight.
PROGRAM PRG_Traffic
VAR
    fbTrafficLight  : FB_TrafficLight;  // the intersection
END_VAR

NETWORK Signal OK
// TRUE while this program runs. Holds the fail-to-red relay in; PLC stop drops it.
    -> GVL_IO.bDO_SignalOk

NETWORK Traffic light
    -> fbTrafficLight(bCarA := GVL_IO.bDI_CarA, bCarB := GVL_IO.bDI_CarB,
                      bPedButton := GVL_IO.bDI_PedButton,
                      bRedA => GVL_IO.bDO_RedA, bYellowA => GVL_IO.bDO_YellowA,
                      bGreenA => GVL_IO.bDO_GreenA, bRedB => GVL_IO.bDO_RedB,
                      bYellowB => GVL_IO.bDO_YellowB, bGreenB => GVL_IO.bDO_GreenB)
END_PROGRAM
