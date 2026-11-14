from PySide6.QtCore import QByteArray, QPoint, Qt, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from gui.focus import OutsideClickRelease

QML = b'''
import QtQuick
import QtQuick.Controls.Basic
Window {
    width: 400; height: 200; visible: true
    TextField { objectName: "cell"; x: 10; y: 10; width: 150; property bool releaseOnOutsideClick: true }
    TextField { objectName: "other"; x: 10; y: 60; width: 150; property bool releaseOnOutsideClick: true }
    TextField { objectName: "plain"; x: 200; y: 10; width: 150 }
}
'''


def click(window, x, y):
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(x, y))
    QTest.qWait(30)


def test_click_elsewhere_releases_marked_fields_only(qt_app):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(QByteArray(QML), QUrl())
    window = component.create()
    assert window is not None, component.errorString()
    OutsideClickRelease(window)
    QTest.qWaitForWindowExposed(window)
    cell, other, plain = (window.findChild(QQuickItem, n) for n in ('cell', 'other', 'plain'))

    click(window, 30, 25)
    assert cell.hasActiveFocus()
    click(window, 30, 25)                       # inside: stays
    assert cell.hasActiveFocus()
    click(window, 300, 180)                     # empty space: let go
    assert not cell.hasActiveFocus()

    click(window, 30, 25)
    click(window, 30, 75)                       # another field: focus moves there
    assert other.hasActiveFocus() and not cell.hasActiveFocus()

    click(window, 220, 25)
    click(window, 300, 180)                     # unmarked fields keep the default behaviour
    assert plain.hasActiveFocus()
    window.close()
