from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.services.sarvam.stt import SarvamSTTService
import inspect

print("Sarvam TTS Default settings:", SarvamTTSService.Settings())
print("TTS init signature:", inspect.signature(SarvamTTSService.__init__))
print("STT init signature:", inspect.signature(SarvamSTTService.__init__))
