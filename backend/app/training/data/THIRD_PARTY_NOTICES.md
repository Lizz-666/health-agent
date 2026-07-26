# Third-Party Notices — Phase 3 Training Knowledge

> Verified: 2026-07-26. This file preserves the pinned upstream copyright and
> license notice for any copied external metadata, as required by the Phase 3
> specification (Source And License Baseline; Safety, Privacy, And Failure
> Handling). The authoritative source manifest is
> `backend/app/training/data/source_manifest.v1.json`.

## 1. hasaneyldrm/exercises-dataset (MIT) — non-media metadata only

- **Pinned version:** commit `7455efae41b330c265e7cd4b78dfa848e7ce5ebd`
- **URL:** https://github.com/hasaneyldrm/exercises-dataset/tree/7455efae41b330c265e7cd4b78dfa848e7ce5ebd
- **License:** MIT
- **Use in Phase 3:** MIT-covered **non-media metadata only** — names, taxonomy
  (category / force / mechanic), equipment, target / secondary muscles, level,
  and schema / import ideas. This material is used only as discovery input for
  the project-authored catalog; every approved exercise is independently
  reviewed and carries its own provenance.
- **Explicitly excluded:** upstream instruction and translation text, and all
  media (`images/`, `videos/`, GIFs, thumbnails, `image`, `gif_url`,
  `media_id`, media attribution payloads).

### License and media exception (retained verbatim from the pinned commit)

```
MIT License

Copyright (c) 2026 Hasan Emir Yıldırım

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation and data files (the "Software"),
to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

------------------------------------------------------------------------------
MEDIA EXCEPTION
------------------------------------------------------------------------------

The MIT license above covers ONLY the code, tooling, dataset structure, and
instruction text/translations in this repository.

It DOES NOT cover the exercise media in the `images/` and `videos/`
directories. That media is © Gym visual (https://gymvisual.com/) and is
included here with the rights holder's written permission, at 180×180
resolution, and must retain the attribution "© Gym visual —
https://gymvisual.com/". Its use and reuse are governed by Gym visual's Terms
& Conditions (https://gymvisual.com/content/3-terms-and-conditions-of-use) and
by `NOTICE.md` in this repository — NOT by the MIT license above. Cloning this
repository does not grant you any license to the media; obtain your own from
Gym visual.
```

**Phase 3 position:** The Health project does **not** clone, copy, or reuse any
of that media. The Phase 3 import adapter explicitly strips and rejects all
media fields; Phase 3 illustrations are original, project-authored local SVGs.
No license to the upstream media is asserted.

## 2. Snouzy/workout-cool — comparison only, no content copied

- **Pinned version:** commit `77f25a922b51be7d96bd051c5d2096959f0d61a8`
- **URL:** https://github.com/Snouzy/workout-cool/tree/77f25a922b51be7d96bd051c5d2096959f0d61a8
- **License:** MIT (upstream repository; no code or data is copied here).
- **Use in Phase 3:** read-only structural comparison of the Prisma exercise,
  program, program-week, session, set, enrollment and progress relationships,
  to contrast plan / execution separation concepts.
- **Excluded:** no code or data is copied; the project does not inherit
  workout-cool's absent risk tier, missing-data gate, contraindications, stop
  conditions, provenance, policy version, or validator model.

### MIT License (retained verbatim from the pinned commit)

```
MIT License

Copyright (c) 2023 Mathias Bradiceanu

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the
following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

## 3. Authoritative references (cited concepts, not copied media)

These sources inform the healthy-adult policy envelope and pre-participation
concepts. No text or media is copied; they are cited for scope and review
provenance only.

- **WHO Guidelines on Physical Activity and Sedentary Behaviour** (2020, ISBN
  978-92-4-001512-8) — © World Health Organization 2020.
  https://www.who.int/publications/i/item/9789240015128
- **ACSM Position Stand, *Resistance Training Prescription for Muscle Function,
  Hypertrophy, and Physical Performance in Healthy Adults*** (2026 official
  position stand; ACSM summary published 2026-03-17) — © American College of
  Sports Medicine. https://acsm.org/resistance-training-guidelines-update-2026/
- **PAR-Q+ / ePARmed-X+** (2025 official individual version, identified
  2026-07-26) — © PAR-Q+ Collaboration. https://eparmedx.com/how-to-cite/

## 4. Project-authored catalog content

The curated exercise catalog (`backend/app/training/data/exercises.v1.json`)
and all illustrations (`assets/training/illustrations/*.svg`) are
**project-authored** original content, reviewed for the personal-development
validation scope only. They are not a clinical endorsement, professional
certification, or public-release approval. The repository currently declares
no distribution license for this project-authored content.
