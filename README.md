# Clueless

Clueless is a Discord bot with a large range of commands featuring:
 - [pxls.space](https://pxls.space) stats visualizer
 - server custom emojis management
 - random images generator using the reddit API
 - pixel art utility commands (outline, crop, color breakdown)
 - misc util commands (ping, echo, ...)

# Installation

## Requirements

- python3 [(version 3.9.6 recommended)](https://www.python.org/downloads/release/python-396/=)

## Register your bot on discord

- See the [discord.py documentation](https://discordpy.readthedocs.io/en/stable/discord.html) on how to create an application and a bot.

- Make sure both `bot` and `application.commands` scopes are selected.

- Put your tokens in a `.env` file following the template in [.env.dist](.env.dist)

## Install the required dependencies

    $ pip install -r requirements.txt


## Start the bot

    $ python3 src/main.py

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

The default prefix is `>`  
Use `>help` to see the list of commands
