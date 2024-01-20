import stable_whisper

model = stable_whisper.load_model('large-v3')

result = model.transcribe('audio.mp3', language = 'bg', fp16=False,
regroup=False)
(
      result
      .split_by_punctuation([('.', ' '), '。', '?', '？', ',', '，'])
      .split_by_gap(.7)
      .merge_by_gap(.10, max_words=4)
      .split_by_length(max_words=7, max_chars=35)
)
result.to_srt_vtt('audio.srt', segment_level =True, word_level=False)



