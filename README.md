<div align="center">
<h1>PCBGolf Challenge</h1>
<h3>How small can you make this PCBA?</h3>
<h3>
  <a href="https://comma.ai/leaderboard#pcbgolf_challenge">Leaderboard</a>
  <span> · </span>
  <a href="https://comma.ai/jobs">comma.ai/jobs</a>
  <span> · </span>
  <a href="https://discord.comma.ai">Discord</a>
  <span> · </span>
  <a href="https://x.com/comma_ai">X</a>
</h3>
</div>

## The Board

The schematic is loosely based on [our panda jungle v2](https://www.comma.ai/shop/panda-jungle), a development and debugging board for comma devices and pandas. This version includes:

* 12V DC input with onboard 5V and 3.3V supplies
* Four [OBD-C](https://github.com/commaai/hardware/blob/master/harness/OBD-C.sch.pdf) device ports with individually controlled power and current monitoring
* Four CAN transceivers and ignition simulation circuitry
* A USB hub and USB-C host connection
* An STM32H725 microcontroller and microSD card slot
* A push button and status LEDs

Explore in your browser with KiCanvas: [PCB layout](https://kicanvas.org/?github=https%3A%2F%2Fgithub.com%2Fcommaai%2FPCBGolf%2Fblob%2Fmaster%2Fpcbgolf.kicad_pcb).

Schematics: [Power](https://kicanvas.org/?github=https%3A%2F%2Fgithub.com%2Fcommaai%2FPCBGolf%2Fblob%2Fmaster%2Fpcbgolf.kicad_sch) · [Microcontroller](https://kicanvas.org/?github=https%3A%2F%2Fgithub.com%2Fcommaai%2FPCBGolf%2Fblob%2Fmaster%2Fpcbgolf_2.kicad_sch) · [USB & microSD](https://kicanvas.org/?github=https%3A%2F%2Fgithub.com%2Fcommaai%2FPCBGolf%2Fblob%2Fmaster%2Fpcbgolf_3.kicad_sch) · [CAN](https://kicanvas.org/?github=https%3A%2F%2Fgithub.com%2Fcommaai%2FPCBGolf%2Fblob%2Fmaster%2Fpcbgolf_4.kicad_sch) · [OBD-C ports](https://kicanvas.org/?github=https%3A%2F%2Fgithub.com%2Fcommaai%2FPCBGolf%2Fblob%2Fmaster%2Fpcbgolf_5.kicad_sch)

![PCBgolf — A little board goes a long way. $1,000 prize.](./assets/pcbgolf.png)

## The Challenge

Your goal is to make the most compact, efficient board that retains the same interfaces and functionality as the original design. The lowest score wins.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./assets/score-dark.svg">
    <img src="./assets/score.svg" width="875" alt="Score = PCBA bounding box volume (mm³) + 50 × number of vias + 5,000 × number of copper layers.">
  </picture>
</p>

### Rules

* The bare PCB must be fully manufacturable by JLCPCB.
* It must be possible to actually assemble the PCBA.
* The assembled product must work and be usable.

### Prize

Lowest score on the [leaderboard](https://comma.ai/leaderboard#pcbgolf_challenge) by **October 12, 2026** wins **$1,000 cash**.

## Submission

Submit a `.zip` file containing your finalized KiCad project and a STEP file of the final assembly [here](https://forms.gle/US88Hg7UR6bBuW3BA).
Competitive scores will be posted on the [leaderboard](https://comma.ai/leaderboard#pcbgolf_challenge) after review. Multiple submissions allowed.
