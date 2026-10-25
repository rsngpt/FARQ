# Library clips for M3 (the "enrolled" team member)

FARQ's source map compares a forwarded video against genuine recordings of the
person it shows. For the demo, one consenting team member is that person. We
need 8 to 10 genuine clips of them.

## Consent (record first, as its own short video, `consent-video-<initials>.mp4`)

> My name is ____. I agree that Team Off-Grid may record videos of my face and
> voice, use them to build and test FARQ during this hackathon, and make test
> fake videos from them on-site, which will only be shown at this event. All of
> it will be deleted afterwards.

## How to record

- Phone camera, **landscape**, 1080p, at eye level, about 1 m away, face and
  shoulders in frame, looking at the camera like a news statement.
- Even light on the face (face a window or lamp, no strong light behind).
- Quiet room. Keep the phone still (lean it on something).
- Speak naturally, each clip **30 to 90 seconds**, about the topic below. No
  script needed; small slips are fine. Move your head and eyebrows as you
  normally do when you talk; don't hold still.
- Hindi, English or both, as you'd normally speak.
- Name files `lib-01-<topic>.mp4`, `lib-02-<topic>.mp4`, ...

## Topics (different topics so the clips are clearly different speeches)

1. Introduce yourself and what you study or work on.
2. Explain how UPI payments work to someone new to them.
3. Your advice on saving money as a student.
4. Describe your hometown.
5. Why people should check before forwarding videos.
6. A recent news story you found interesting.
7. How to set a strong password.
8. A short "official announcement": a made-up college event (date, time, place).
9. (optional) Your favourite food and how it's made.
10. (optional) What you'd build with AI if you had a month.

Please **don't** mention real investment schemes, real phone numbers or real UPI
IDs. Topic 8 should be clearly fictional.

## Where they go

Send them to the team lead. They go in the repo's `samples/library/` folder,
which git ignores, so face videos are never committed or pushed.

## What happens to them

- Each clip is added to FARQ's library (frame fingerprints, transcript,
  phrase embeddings).
- Test fakes are made on-site from them with FFmpeg: the picture from one clip
  with the voice from another. No AI lip-sync tool is used unless the team
  decides to add and declare one.
