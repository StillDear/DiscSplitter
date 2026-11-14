import QtQuick
// Staggered fade-and-rise for ListView populate/add. Rows finish fully visible
// even when motion is reduced (durations collapse to 0).
Transition {
    id: enter
    SequentialAnimation {
        PropertyAction { property: "opacity"; value: 0 }
        PauseAnimation { duration: Theme.animate ? Math.min(enter.ViewTransition.index, 12) * 22 : 0 }
        ParallelAnimation {
            NumberAnimation { property: "opacity"; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
            NumberAnimation {
                property: "y"; from: enter.ViewTransition.destination.y + (Theme.animate ? 8 : 0)
                to: enter.ViewTransition.destination.y; duration: Theme.normal; easing.type: Easing.OutCubic
            }
        }
        PropertyAction { property: "opacity"; value: 1 }
    }
}
