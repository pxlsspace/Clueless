<p align="center">
  <a>
    <img src="https://cdn.discordapp.com/avatars/856207006217928746/1168aeb243d2e4e221a7073cd87f2ec9.webp?size=1024" alt="Logo" width="80" height="80">
  </a>
  <h3 align="center">Clueless</h3>
  <p align="center">
    A pxls.space discord utility bot and more!
    <br />
    <a href="https://discord.gg/5MVDCq53vC">Discord Server</a>
    ·
    <a href="https://discord.com/api/oauth2/authorize?client_id=856207006217928746&permissions=536401542208&scope=applications.commands%20bot">Invite Clueless</a>
  </p>
</p>

<p align="center">
    <a href="https://discord.gg/5MVDCq53vC">
        <img src="https://img.shields.io/discord/936560830462451762?style=flat-square&color=5865F2&label=discord&logo=discord&logoColor=FFFFFF" alt="Discord">
    </a>
    <a href="https://github.com/GrayTurtles/Clueless">
        <img src="https://img.shields.io/badge/version-2.0+-blue?style=flat-square" alt="Discord">
    </a>
    <a href="https://github.com/DisnakeDev/disnake">
        <img src="https://img.shields.io/badge/lib-disnake%202.4-blue?style=flat-square" alt="Disnake">
    </a>
    <br/>
    <a href="https://github.com/GrayTurtles/Clueless">
        <img src="https://img.shields.io/github/commit-activity/m/GrayTurtles/Clueless?style=flat-square&color=green" alt="Activity">
    </a>
</p>


# About
Clueless is a Discord bot made to interract with [pxls.space](https://pxls.space), it includes a large range of commands.

The main features are:
 - **User stats**: get graph of users' speed, leaderboards, user information and more.
 - **Template creation**: generate a template from an image, detemplatize an existing template and check its progress.
- **Template tracking**: track your template's progress over time with visual graphs and a lot of stats. (average speed, ETA)
 - **Pxls general stats**: canvas elapsed time, percentage of virgin pixels, the average number of users online, the average cooldown ...
 - **Pixel art tools**: outlines, pixel text, crop, upscale/downscale, color breakdown, ...
 - **Customization**: All the graphs and tables made by Clueless are customizable using themes and fonts.

There are also some non-pxls related commands:
 - Server custom emojis management.
 - Random image getter. (using the reddit API)
 - Image manipulation. (rainbowfy, colorify)
 - Lyrics: get the lyrics of a song you're playing on Spotify or search for a song.
# Installation

I would prefer that you do not run an instance of this bot. If you wish to use it, you can invite it to your own server or join the support server linked above.

## Requirements

- python3 [(version 3.9.5 recommended)](https://www.python.org/downloads/release/python-395/)
- [poetry](https://python-poetry.org/docs/master/#installing-with-the-official-installer)
## 1) Register your bot on discord

- See the [discord.py documentation](https://discordpy.readthedocs.io/en/stable/discord.html) on how to create an application and a bot.

- Make sure both `bot` and `application.commands` scopes are selected.

- Put your tokens in a `.env` file following the template in [.env.dist](.env.dist)

## 2) Install the required dependencies

    $ poetry install


## 3) Start the bot

    $ poetry run python src/main.py

# Deploy on a distant host (with pm2)

## Install pm2  

You need to install pm2 on your local machine and on the host:
- install [Node.js and npm](https://nodejs.org/en/).
- `npm install pm2 -g`
- check installation with `pm2 -v`  

## Setup
Edit [`ecosystem.sample.js`](ecosystem.sample.js) with your host information and rename it to `ecosystem.config.js`

On your local machine:

    pm2 deploy production setup

## Deploy

    pm2 deploy production

If you get an error, make sure to update your `.env` information on the host too.

For more information, see [this deploy pm2 guide](https://gist.github.com/hoangmirs/b2cb60e0aa60019f0c8b13927ce9d0a2).

# Commands
This bot uses both prefix and slash commands. The default prefix is `>`.

Use `>help` or `/help` on a server with Clueless to see the list of commands
