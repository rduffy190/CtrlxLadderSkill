// E_TrafficState: steps of the two-lane traffic light, in ring order.
// AllRedToA is 0 so power-up starts with an all-red clearance. Keep YellowB last:
// FB_TrafficLight treats any value above it as invalid.
{attribute 'qualified_only'}
TYPE E_TrafficState :
(
    AllRedToA := 0,     // both red, lane A gets green next
    GreenA,             // A green, B red; rests here until there is demand
    YellowA,            // A yellow, B red
    AllRedToB,          // both red, lane B gets green next
    GreenB,             // B green, A red; rests here until there is demand
    YellowB             // B yellow, A red
) UINT;
END_TYPE
