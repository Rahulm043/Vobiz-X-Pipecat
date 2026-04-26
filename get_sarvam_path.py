import inspect
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.services.sarvam.stt import SarvamSTTService
print("TTS Path:", inspect.getfile(SarvamTTSService))
print("STT Path:", inspect.getfile(SarvamSTTService))
