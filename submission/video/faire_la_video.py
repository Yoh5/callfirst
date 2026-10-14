"""The demo video, built so the narration decides the timing.

    python submission/video/faire_la_video.py

Every hackathon video drifts the same way: the pictures are cut first, the
voice is recorded second, and the two are nudged together by hand until they
roughly agree. Nudging by hand is exactly the kind of number this project
refuses everywhere else, so it is refused here too.

The order is reversed. Each scene owns a sentence. The sentence is spoken
first, its wav is measured to the sample, and the scene is then held on screen
for exactly that long. Audio and picture cannot drift, because nothing is
timed twice.

Three things this script will not do:

- **It will not go over the limit.** Both rules this video is cut for say
  *less than three minutes*, and Amazon adds that judges are not required to
  watch past it. So the build fails if the total reaches 3:00, rather than
  shipping something a judge is entitled to stop watching.
- **It will not invent a screen.** Every frame of the product is a real
  capture of the running app, taken from `submission/video/captures/`, and the
  two terminal panels are the committed output files, read at build time.
- **It will not claim a voice it does not have.** The narration is synthetic
  (`edge-tts`), the submission says so, and the last scene says so on screen.

Needs `edge-tts` (`pip install edge-tts`) and the ffmpeg that ships with
`imageio-ffmpeg`. Nothing else.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import textwrap
import wave
from pathlib import Path

import imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent.parent
CAPTURES = ICI / "captures"
TRAVAIL = ICI / "_travail"

L, H = 1280, 720
HAUTEUR_CAPTURE = 585           # ce que rend le navigateur, pixel pour pixel
BANDE = H - HAUTEUR_CAPTURE     # 135 px de légende sous l'image

CREME = (250, 247, 242)
ENCRE = (26, 32, 44)
ENCRE_2 = (90, 100, 115)
MARINE = (31, 78, 121)
ROUGE = (176, 42, 42)

#: Une voix neuronale, pas la voix Windows : à ce débit la différence
#: s'entend, et c'est la seule piste de la vidéo.
VOIX = "en-US-AndrewNeural"
DEBIT = "-6%"                   # un cran sous le défaut : des chiffres à dire

LIMITE = 180.0                  # secondes. Les deux règlements disent « moins de 3 min ».

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def police(nom: str, taille: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(f"C:/Windows/Fonts/{nom}", taille)


# --------------------------------------------------------------------------- #
# Les scènes. Le texte est la source : il est dit, puis il mesure la scène.
# --------------------------------------------------------------------------- #
class Scene:
    def __init__(self, cle: str, texte: str, legende: str, *,
                 capture: str | None = None, titre: str | None = None,
                 sous_titre: str | None = None, fichier: str | None = None,
                 lignes: int = 18, accent: tuple[int, int, int] = MARINE) -> None:
        self.cle, self.texte, self.legende = cle, texte, legende
        self.capture, self.titre, self.sous_titre = capture, titre, sous_titre
        self.fichier, self.lignes, self.accent = fichier, lignes, accent
        self.secondes = 0.0


SCENES = [
    Scene("01-ouverture",
          "A phone call says your grandson is in jail, or that a federal agent "
          "needs your savings kept safe. Then a courier comes to the door to "
          "collect the cash, or the gold. The F B I counted one thousand seven "
          "hundred and thirty-seven of these doorstep pickups, about one hundred "
          "and eighty-six million dollars, in two and a half years.",
          "FBI IC3, 2023 to May 2025",
          titre="Courier scams end\nat the front door.",
          sous_titre="1,737 doorstep pickups. $186 million."),

    Scene("02-pourquoi",
          "A doorbell that alerts on strangers does not help, because the victim "
          "is expecting the courier. So Call First watches for something else: a "
          "visitor nobody declared in advance, and the door opening for them.",
          "the whole design, in one line",
          titre="The victim is\nexpecting the courier.",
          sous_titre="So we do not alert on strangers."),

    Scene("03-consentement",
          "Margaret switches it on herself, and chooses who is told: her daughter "
          "Sarah. While it is off, nothing is recorded and nobody is told. That is "
          "how it arrives.",
          "the resident switches it on — it is never switched on for her",
          capture="01-protection-off.jpg"),

    Scene("04-carillon",
          "Someone Margaret was not expecting rings. Indoors, the chime says: "
          "before you hand anything over, call your family first, and ask for "
          "your family word. The one code a scammer cannot know.",
          "the reminder played, inside the house",
          capture="03-reminder-played.jpg"),

    Scene("05-porte",
          "The door opens anyway. Sarah is told at once, with the doorbell's "
          "still image, and one instruction: call Margaret now.",
          "the door sensor saw it — the still is an illustration, nobody is identified",
          capture="04-family-call-now.jpg", accent=ROUGE),

    Scene("06-refus",
          "Scammers coach their victims to make the courier look expected. A "
          "delivery message asking someone to collect gold for safekeeping is "
          "refused, and told why. A model may help read the message. It decides "
          "nothing.",
          "refused by code that reads the message itself",
          capture="07-collection-refused.jpg", accent=ROUGE),

    Scene("07-ambigu",
          "And when a real notice is genuinely unclear, it does not guess. The "
          "message says Tuesday. Call First asks which one.",
          "a guess here would open the door for the wrong visitor",
          capture="08-which-tuesday.jpg"),

    Scene("08-contre-la-residente",
          "The scammer's next move is to talk her out of it. So every change that "
          "weakens the protection tells the family at once, and a pause ends by "
          "itself.",
          "Margaret paused it — Sarah already knows",
          capture="10-paused-family.jpg"),

    Scene("09-feuille",
          "Sarah also gets a report sheet, prepared from what the front door "
          "recorded and ready for the F B I and the F T C. Nothing on it has been "
          "sent to anyone. Reporting is her decision, not the software's.",
          "the handover is the only part of this scam that happens in the open",
          capture="14-report-sheet.jpg"),

    Scene("10-chiffres-page",
          "Through an emulator that drops one webhook in ten, sixty courier "
          "visits: every family was told, and no reminder played twice. Forty-eight "
          "rules were broken on purpose, to check that a test fails for each one.",
          "the claim, on the page a visitor reads",
          capture="13-measured-not-demonstrated.jpg"),

    Scene("11-chiffres-fichier",
          "Those are not three numbers on a slide. They are read out of the files "
          "the runs wrote, and a test fails if the page and the files ever stop "
          "agreeing. It has already caught one.",
          "submission/chaos.txt and submission/mutate.txt, read at build time",
          fichier="chaos+mutate", lignes=16),

    Scene("12-refus-de-faire",
          "No faces recognised. No police called. Nothing without Margaret's say, "
          "and one button deletes everything. And without a door sensor, a handover "
          "under a minute is missed — that row is on the page too.",
          "Call First — github.com/Yoh5/callfirst (MIT) · narration is synthetic",
          capture="12-will-not-do.jpg"),
]


# --------------------------------------------------------------------------- #
# La voix
# --------------------------------------------------------------------------- #
def dire(scene: Scene) -> Path:
    """Rend la phrase, puis la convertit en wav pour pouvoir la mesurer."""
    mp3, wav = TRAVAIL / f"{scene.cle}.mp3", TRAVAIL / f"{scene.cle}.wav"
    if not wav.exists():
        # `--rate=-6%` et non `--rate -6%` : argparse lit un débit négatif
        # comme une option courte et rend un code 2.
        subprocess.run([sys.executable, "-m", "edge_tts", "--voice", VOIX,
                        f"--rate={DEBIT}", "--text", scene.texte,
                        "--write-media", str(mp3)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([FFMPEG, "-y", "-i", str(mp3), "-ac", "1", "-ar", "48000",
                        str(wav)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return wav


def duree(wav: Path) -> float:
    with wave.open(str(wav)) as f:
        return f.getnframes() / f.getframerate()


def coller(wavs: list[Path], silences: list[float], sortie: Path) -> float:
    """Une seule piste : [silence] phrase [silence] phrase ...

    Les blancs sont ici, pas dans l'image, pour qu'il n'existe qu'un seul
    endroit où le temps est décidé.
    """
    with wave.open(str(wavs[0])) as f:
        params = f.getparams()
    morceaux: list[bytes] = []
    muet = b"\x00" * (params.sampwidth * params.nchannels)
    for wav, blanc in zip(wavs, silences):
        with wave.open(str(wav)) as f:
            morceaux.append(f.readframes(f.getnframes()))
        morceaux.append(muet * round(blanc * params.framerate))
    with wave.open(str(sortie), "wb") as f:
        f.setparams(params)
        for m in morceaux:
            f.writeframes(m)
    return duree(sortie)


# --------------------------------------------------------------------------- #
# L'image
# --------------------------------------------------------------------------- #
def replier(d: ImageDraw.ImageDraw, texte: str, f: ImageFont.FreeTypeFont,
            largeur: int) -> list[str]:
    lignes: list[str] = []
    for paragraphe in texte.split("\n"):
        mots, courante = paragraphe.split(), ""
        for mot in mots:
            essai = f"{courante} {mot}".strip()
            if d.textlength(essai, font=f) <= largeur:
                courante = essai
            else:
                lignes.append(courante)
                courante = mot
        lignes.append(courante)
    return lignes


def bande_legende(img: Image.Image, scene: Scene) -> None:
    d = ImageDraw.Draw(img)
    d.rectangle([0, HAUTEUR_CAPTURE, L, H], fill=ENCRE)
    d.rectangle([0, HAUTEUR_CAPTURE, L, HAUTEUR_CAPTURE + 4], fill=scene.accent)
    f = police("seguisb.ttf", 27)
    lignes = replier(d, scene.legende, f, L - 120)
    y = HAUTEUR_CAPTURE + (BANDE - len(lignes) * 36) // 2 + 2
    for ligne in lignes:
        d.text((60, y), ligne, font=f, fill=(238, 240, 244))
        y += 36


def image_capture(scene: Scene) -> Image.Image:
    fond = Image.new("RGB", (L, H), CREME)
    capture = Image.open(CAPTURES / scene.capture).convert("RGB")
    if capture.size != (L, HAUTEUR_CAPTURE):
        capture = capture.resize((L, HAUTEUR_CAPTURE), Image.LANCZOS)
    fond.paste(capture, (0, 0))
    bande_legende(fond, scene)
    return fond


def image_titre(scene: Scene) -> Image.Image:
    fond = Image.new("RGB", (L, H), CREME)
    d = ImageDraw.Draw(fond)
    gros = police("segoeuib.ttf", 62)
    petit = police("segoeui.ttf", 31)
    lignes = scene.titre.split("\n")
    hauteur = len(lignes) * 74 + 54
    y = (HAUTEUR_CAPTURE - hauteur) // 2
    # Le filet va AU-DESSUS du titre. Posé entre le titre et le sous-titre, il
    # tombait dans la jambe des descendantes de la dernière ligne et se lisait
    # comme un texte barré.
    d.rectangle([90, y - 34, 90 + 96, y - 30], fill=scene.accent)
    for ligne in lignes:
        d.text((90, y), ligne, font=gros, fill=ENCRE)
        y += 74
    d.text((90, y + 22), scene.sous_titre, font=petit, fill=scene.accent)
    bande_legende(fond, scene)
    return fond


def image_fichier(scene: Scene) -> Image.Image:
    """Les deux sorties mesurées, lues dans le dépôt au moment du rendu."""
    fond = Image.new("RGB", (L, H), (22, 25, 30))
    d = ImageDraw.Draw(fond)
    mono = police("consola.ttf", 19)
    titre = police("seguisb.ttf", 24)

    def derniers(nom: str, n: int) -> list[str]:
        texte = (RACINE / "submission" / nom).read_text(
            encoding="utf-8", errors="replace").rstrip().splitlines()
        return texte[-n:]

    # Empilées, pas côte à côte : les lignes de `chaos.txt` font plus de
    # quatre-vingts caractères, et en deux colonnes elles se marchaient dessus.
    blocs = (("chaos.txt", derniers("chaos.txt", 4), 34),
             ("mutate.txt", derniers("mutate.txt", 10), 230))
    #: Les deux seuls chiffres que la narration prononce. Ils sont verts parce
    #: qu'ils sont ce qui est affirmé ; le reste du fichier est là pour qu'on
    #: voie qu'il n'a pas été choisi.
    AFFIRME = ("families told 60/60", "played twice 0", "48/48 mutations caught")
    for nom, lignes, haut in blocs:
        d.text((60, haut), nom, font=titre, fill=(120, 190, 255))
        y = haut + 44
        for ligne in lignes:
            dit = any(a in ligne for a in AFFIRME)
            d.text((60, y), ligne[:96], font=mono,
                   fill=(130, 220, 160) if dit else (200, 206, 214))
            y += 27
    bande_legende(fond, scene)
    return fond


def rendre(scene: Scene) -> Image.Image:
    if scene.titre:
        return image_titre(scene)
    if scene.fichier:
        return image_fichier(scene)
    return image_capture(scene)


def fondu(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    return Image.blend(a, b, t)


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--sortie", default=str(ICI / "callfirst-demo.mp4"))
    ap.add_argument("--avant", type=float, default=0.35,
                    help="blanc avant la première phrase")
    ap.add_argument("--entre", type=float, default=0.55,
                    help="blanc entre deux scènes")
    ap.add_argument("--apres", type=float, default=1.1,
                    help="blanc après la dernière phrase")
    args = ap.parse_args()

    TRAVAIL.mkdir(exist_ok=True)
    manquantes = [s.capture for s in SCENES
                  if s.capture and not (CAPTURES / s.capture).exists()]
    if manquantes:
        print("Captures manquantes :", ", ".join(manquantes))
        return 1

    print("Narration")
    wavs = []
    for scene in SCENES:
        wav = dire(scene)
        scene.secondes = duree(wav)
        wavs.append(wav)
        print(f"  {scene.cle:<22} {scene.secondes:5.2f} s")

    silences = [args.entre] * len(SCENES)
    silences[-1] = args.apres
    piste = TRAVAIL / "narration.wav"
    total_audio = args.avant + coller(wavs, silences, piste)

    print(f"\nTotal parlé + blancs : {total_audio:.2f} s")
    if total_audio >= LIMITE:
        print(f"ECHEC : {total_audio:.1f} s atteint la limite de {LIMITE:.0f} s.")
        print("Les deux règlements disent « moins de trois minutes », et Amazon")
        print("ajoute que les jurés ne sont pas tenus de regarder au-delà.")
        print("Raccourcir une phrase, pas la vidéo.")
        return 1

    sortie = Path(args.sortie)
    muette = TRAVAIL / "muette.mp4"
    transition = 0.4

    print("\nImages")
    images = [rendre(s) for s in SCENES]
    with imageio.get_writer(muette, fps=args.fps, codec="libx264", quality=8,
                            macro_block_size=1) as film:
        for _ in range(round(args.avant * args.fps)):
            film.append_data(np.asarray(images[0]))
        for i, (scene, img) in enumerate(zip(SCENES, images)):
            tenue = scene.secondes + (silences[i] - transition
                                      if i < len(SCENES) - 1 else silences[i])
            for _ in range(round(tenue * args.fps)):
                film.append_data(np.asarray(img))
            if i < len(SCENES) - 1:
                for k in range(round(transition * args.fps)):
                    t = (k + 1) / round(transition * args.fps)
                    film.append_data(np.asarray(fondu(img, images[i + 1], t)))
            print(f"  {scene.cle:<22} {tenue:5.2f} s")

    print("\nMontage")
    subprocess.run([FFMPEG, "-y", "-i", str(muette), "-itsoffset", str(args.avant),
                    "-i", str(piste), "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                    "-shortest", str(sortie)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    taille = sortie.stat().st_size / 1e6
    minutes, secondes = divmod(total_audio, 60)
    print(f"\n{sortie}")
    print(f"  {int(minutes)}:{secondes:04.1f} | {taille:.1f} Mo | {L}x{H} a {args.fps} fps")
    print(f"  marge sous la limite : {LIMITE - total_audio:.1f} s")

    # Les chapitres YouTube sortent du montage, pas du plan de tournage. Écrits
    # à la main ils tombent à côté dès qu'une phrase change de longueur, et un
    # juré qui clique sur un chapitre et atterrit au mauvais endroit a appris
    # quelque chose sur le soin apporté au reste.
    chapitres = ICI / "chapitres.txt"
    lignes, t = [], args.avant
    for i, scene in enumerate(SCENES):
        m, s = divmod(int(t), 60)
        lignes.append(f"{m}:{s:02d} {scene.legende}")
        t += scene.secondes + silences[i]
    # YouTube exige un premier chapitre à 0:00 et au moins dix secondes entre deux.
    lignes[0] = "0:00 " + SCENES[0].legende
    chapitres.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print(f"\nChapitres YouTube dans {chapitres}")
    for ligne in lignes:
        print("  " + ligne)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
