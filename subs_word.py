import stable_whisper

model = stable_whisper.load_model('large-v3')

result = model.transcribe('audio.mp3', language = 'bg', fp16=False,
regroup=False)
(
    result
    .split_by_punctuation([('.', ' '), '。', '?', '？', (',', ' '), '，'])
    .split_by_length(max_chars=10)

)

result.to_srt_vtt('audio.srt', segment_level = True, word_level=False)




