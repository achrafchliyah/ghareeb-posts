# غريب القرآن — daily Instagram posts

`posts/<NNN>/` holds approved carousels (8 JPEGs + `caption.txt`), pushed here by `python run.py approve` from the
generator project. Every day `.github/workflows/post.yml` runs `publish.py`, which posts the lowest-numbered episode
not yet in `posted.json` through the Instagram API and records it.

- Secrets: `IG_ACCESS_TOKEN`, `IG_USER_ID` (set by `python run.py instagram-login` on the PC).
- Test without posting: Actions → *Post to Instagram* → *Run workflow* (dry run is ticked by default).
- Change the time: the `cron` line in the workflow (UTC).

Content is adapted from the «غريب القرآن» series by الشيخ د. عبدالرحمن بن معاضة الشهري (مركز تفسير للدراسات القرآنية).
