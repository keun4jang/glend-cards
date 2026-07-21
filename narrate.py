"""
릴스 나레이션(TTS) 모듈 — 텍스트를 한국어 음성 mp3로 변환.

엔진 선택: 환경변수 TTS_ENGINE
  - "edge"   (기본) : edge-tts, 마이크로소프트 신경망 음성. 음질 최고, API키 불필요.
                      단, GitHub Actions의 데이터센터 IP가 간헐적으로 차단될 수 있음(403/무음).
                      그 경우 TTS_ENGINE=kokoro 로 전환.
  - "kokoro"        : Kokoro TTS(로컬, Apache-2.0). 차단·ToS 걱정 없음. CPU로 CI에서 동작.
                      requirements: kokoro, soundfile, misaki[ko]

사용: synthesize("안녕하세요", "out.mp3")  -> mp3 파일 생성, 성공 시 True
"""
import os
import asyncio

ENGINE = os.getenv("TTS_ENGINE", "edge").strip().lower()
EDGE_VOICE = os.getenv("EDGE_VOICE", "ko-KR-InJoonNeural")  # 남성. 여성은 ko-KR-SunHiNeural
EDGE_RATE = os.getenv("EDGE_RATE", "+25%")   # 말 속도. 너무 빠르면 어색 → +25% 정도가 자연스러움
EDGE_PITCH = os.getenv("EDGE_PITCH", "+0Hz")  # 음높이
KOKORO_VOICE = os.getenv("KOKORO_VOICE", "kf_default")


def _synth_edge(text, out_path):
    import edge_tts

    async def _run():
        comm = edge_tts.Communicate(text, EDGE_VOICE, rate=EDGE_RATE, pitch=EDGE_PITCH)
        await comm.save(out_path)

    asyncio.run(_run())
    # edge-tts는 차단 시 0바이트 파일을 남기기도 함 → 크기 검증
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 1024:
        raise RuntimeError("edge-tts가 오디오를 반환하지 않음(차단 가능성). TTS_ENGINE=kokoro 권장.")
    return True


def _synth_kokoro(text, out_path):
    import soundfile as sf
    import numpy as np
    from kokoro import KPipeline

    pipeline = KPipeline(lang_code="k")  # 'k' = Korean
    audio_chunks = []
    for _, _, audio in pipeline(text, voice=KOKORO_VOICE):
        audio_chunks.append(audio)
    if not audio_chunks:
        raise RuntimeError("kokoro가 오디오를 생성하지 못함")
    audio = np.concatenate(audio_chunks)
    wav_path = out_path.rsplit(".", 1)[0] + ".wav"
    sf.write(wav_path, audio, 24000)
    # mp3로 요청됐으면 ffmpeg로 변환
    if out_path.endswith(".mp3"):
        import subprocess
        subprocess.run(["ffmpeg", "-y", "-i", wav_path, out_path],
                       check=True, capture_output=True)
        os.remove(wav_path)
    return True


def synthesize(text, out_path):
    text = (text or "").strip()
    if not text:
        raise ValueError("빈 텍스트는 나레이션할 수 없음")
    if ENGINE == "kokoro":
        return _synth_kokoro(text, out_path)
    return _synth_edge(text, out_path)


if __name__ == "__main__":
    synthesize("이것은 글렌드 릴스 나레이션 테스트입니다.", "narration_test.mp3")
    print(f"OK ({ENGINE}) -> narration_test.mp3")
