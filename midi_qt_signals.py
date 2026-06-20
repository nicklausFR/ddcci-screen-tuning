from PySide6.QtCore import QObject, Signal

class MidiQTSignalBus(QObject):
    """
    Qt signal bus for received MIDI events.

    Signal :
    - midi_update(key: str, value: int) :
        Sends a state change from a MIDI fader.
        key : 'brightness', 'contrast', 'nightlight'
        value : valeur entre 0 et 100
    """
    midi_update = Signal(str, int)

# Global instance used by the project
bus = MidiQTSignalBus()
