# La vidéo sur YouTube — titre, description, chapitres

Le règlement exige une vidéo **publique** sur YouTube ou Vimeo, en anglais, de
moins de trois minutes. Donc tout ce qui suit est en anglais : c'est ce que le
juré lit.

Deux choses que la page YouTube doit faire, et qu'on oublie parce qu'on pense
d'abord à la vidéo :

- **être lisible sans le son.** Un juré qui parcourt des dizaines de projets en
  regarde une partie en silence. La description doit donc dire ce que la vidéo
  montre, pas inviter à la regarder.
- **porter les liens.** C'est la seule page de la soumission qu'on atteint
  depuis l'extérieur de Devpost.

---

## Titre (99 caractères — la limite est 100)

```
Call First — the Ring doorbell says "call your family first" before she hands anything over
```

L'alternative, si tu préfères nommer l'arnaque d'entrée :

```
Call First — courier scams end at the front door. So does this. (Amazon Developer Hackathon)
```

---

## Description — à coller telle quelle

```
Courier scams are the one kind of elder fraud that has to come to the house. The
call, the fear and the secrecy happen at a distance; the handover does not. The
FBI counted 1,737 doorstep pickups, about $186 million, from 2023 to May 2025.

Alerting on strangers fails, because the victim is expecting the courier. Call
First watches for something else — a visitor nobody declared in advance, and the
door opening for them.

· An unexpected visitor rings: the Ring chime plays a reminder that points to the
  family's code word, the one code a scammer cannot know.
· The door opens: the trusted people are emailed at once, with the doorbell's
  still image, a printable report sheet for IC3 and the FTC, and how sure the
  system is.
· Every attempt to weaken the protection — pausing, switching off, declaring a
  visit for today — is told to the family first, because the scammer's next move
  is to talk her out of it.

Measured, not demonstrated: 60 courier visits through an emulator that drops one
webhook in ten, every family whose doorbell was seen told, no reminder played
twice. 261 tests, and 48 rules broken on purpose to check that a test fails for
each. The false alerts and the misses are published next to the successes.

No faces are recognised. No police are called. Nothing happens without the
resident's say, and one button deletes everything.

CHAPTERS
0:00 A courier at the door
0:25 Why alerting on strangers fails
0:45 The run, with a door sensor
1:25 Without a sensor
1:40 The tool turned against the resident
2:05 The numbers
2:30 What it will not do

LINKS
Code (MIT): https://github.com/Yoh5/callfirst
Try it: https://callfirst-bgtj.onrender.com/try
Pull request upstream: https://github.com/josepha-mayo/ring-sandbox/pull/10

BUILT ON
The Ring Partner API, for the Ring track of the Amazon Developer Hackathon 2026.
Ring publishes no simulator, so every measurement above was taken against
ring-sandbox (MIT) — an open source emulator written by someone else, which we
read in full and pinned by hash: https://github.com/josepha-mayo/ring-sandbox

The still image shown in the video is a drawing, marked ILLUSTRATION. This
product identifies nobody.
```

---

## Avant de publier

- **Visibilité : publique.** Pas « non répertoriée » — le règlement dit
  *publicly visible*.
- **Les horodatages des chapitres sont ceux du plan**, pas de ton montage.
  Corrige-les après l'export, sinon ils tombent au mauvais endroit. YouTube
  exige que le premier soit `0:00`, qu'il y en ait au moins trois, et au moins
  dix secondes entre deux.
- **Sous-titres** : laisse YouTube les générer, puis **relis-les**. Il écrit
  « ring sandbox » n'importe comment et massacre les chiffres (`52 of 60`).
- **Pas de musique sous droits** — le règlement l'interdit explicitement.
- La dernière ligne sur l'illustration n'est pas de la modestie : Ring est
  attaqué en justice sur la reconnaissance faciale, et un juré qui voit une
  image de visiteur se posera la question. Mieux vaut y répondre avant.
