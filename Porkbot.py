# This example requires the 'message_content' privileged intent to function.

import asyncio
import os
from typing import SupportsIndex
import discord
import re
import audioop
import json
import yt_dlp
from random import choices, shuffle
from discord import app_commands, Interaction
from discord.ui import Button, View, TextInput, button, Modal


intents = discord.Intents.default()
client = discord.Client(intents=intents.all())
guild = client.get_guild(727745299614793728)
tree = app_commands.CommandTree(client)
title_queue = []
loop = False
loopOne = False
pattern = re.compile(r'^https:\/\/[^\s\/$.?#].[^\s]*$')
vc = None
currEmbed = None


class setList(list):
    def __init__(self): self.lst = []
    def append(self, object) -> None:
        if len(self.lst) > 4:
            print("too big")
            self.lst.pop(0)
        elif len(self.lst) == 0 or object != self.lst[-1]:
            return self.lst.append(object)
    def __len__(self) -> int: return len(self.lst)
    def pop(self, index: SupportsIndex = -1) -> tuple: return self.lst.pop(index)


class AudioSourceTracked(discord.PCMVolumeTransformer):
    def __init__(self, source: discord.AudioSource, volume: float):
        super().__init__(original=source, volume=volume)
        self.count_20ms = 0
    def read(self) -> bytes:
        ret = self.original.read()
        if ret:
            self.count_20ms += 1
        return audioop.mul(ret, 2, min(self._volume, 2.0))
    
    @property
    def progress(self) -> str:
        currTime = self.count_20ms * 0.02
        hours = currTime//3600
        currTime-=(hours*3600)
        minutes = currTime//60
        currTime-=(minutes*60)
        currTimeString = f"{str(int(hours))+':' if int(hours) > 0 else ''}{str(int(minutes))+':' if int(minutes) > 0 else '0:'}{'0'+str(int(currTime)) if int(currTime) < 10 else str(int(currTime))}"
        return currTimeString
    

FFMPEG_OPTIONS = {
    'before_options':
    '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -probesize 200M',
    'options': '-vn'
}

class UrlField(Modal, title='Youtube URL'):
    def __init__(self, url):
        super().__init__(timeout=10)
        self.url = url
    urlField = TextInput(label="Youtube URL Here:", required=True)
    async def on_submit(self, interaction: Interaction):
        if pattern.match(self.urlField.value) is not None:
            self.url = self.urlField.value
            await interaction.response.send_message(content="URL Received", delete_after=0.5)
            self.stop()
        else:
            await interaction.response.send_message(content="Invalid URL!!!", delete_after=2)
            self.stop()
        

class VolField(Modal, title='Volume Settings'):
    def __init__(self, volume):
        super().__init__(timeout=10)
        self.vol = volume
    volField = TextInput(label="Enter Volume Here (0-200)", required=True)
    async def on_submit(self, interaction: Interaction):
        if self.volField.value.isdigit() and 0<=int(self.volField.value)<=200:
            self.vol = float(self.volField.value)/100
            await interaction.response.send_message(content=f"Volume set to {int(self.vol*100)}", delete_after=0.5)
            self.stop()
        else:
            await interaction.response.send_message(content=f"Invalid Volume!", delete_after=0.5)
            self.stop()



class Player(View):
    def __init__(self, vc: discord.VoiceClient, currEmbed: discord.Embed, *, timeout=21600):
        self.FFMPEG_OPTIONS = {
            'before_options':
            '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -probesize 200M',
            'options': '-vn'
        }
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        self.ydl_playlist_opts = {
            'format': 'worstaudio',
            'outtmpl': '%(playlist)s/%(playlist_index)s - %(title)s.%(ext)s',
            'quiet': True,
            'extract_flat':'in_playlist',
            'skip_download': True,
        }
        
        self.url = ""
        self.vc = vc
        self.volume = 1.0
        self.paused = False
        self.interact = None
        self.currembed = currEmbed
        self.dead = False
        self.loopOne = loopOne
        super().__init__(timeout=timeout)
        self.queue = []
        self.looping = loop
        self.queueButton = None
        self.first = True
        self.prev = False
        self.songHist = setList()
        self.totalHours = 0
        self.totalMinutes = 0
        self.totalSeconds = 0


    @button(emoji="↩", label="Add To Queue", row=2, custom_id="queue")
    async def addToQueue(self, inter: Interaction, button: Button):
        self.queueButton = button
        self.queueButton.disabled = True
        print(inter.user.display_name)
        if inter.user.voice is not None and inter.user.voice.channel.id == self.vc.channel.id:
            if inter.guild.voice_client is None:
                self.vc = inter.user.voice.channel.connect()
            linkModal = UrlField(url="")
            await inter.response.send_modal(linkModal)
            await inter.edit_original_response(embed=await self.genEmbed(["Loading Video...", "https://cdn.discordapp.com/attachments/1267870147394277438/1268695496915025920/loading7_green.gif?ex=66ad5c41&is=66ac0ac1&hm=32b911757057d25f02e09d697c6e920a4e1fa9ff470e96227c378928c822f377&", "N/A", "Volume N/A"]), view=self)
            timedout = await linkModal.wait()
            if timedout:
                self.queueButton.disabled = False
                await inter.edit_original_response(embed=self.currembed, view=self)
                await inter.channel.send("You didnt put any URLs in time!", delete_after=5)
            elif len(linkModal.url) == 0 or pattern.match(linkModal.url) is None:
                self.queueButton.disabled = False
                await inter.edit_original_response(embed=self.currembed, view=self)
            elif "list=" in linkModal.url:
                await inter.edit_original_response(embed=await self.genEmbed(["Playlist is being processed...", "https://cdn.discordapp.com/attachments/1267870147394277438/1268695496915025920/loading7_green.gif?ex=66ad5c41&is=66ac0ac1&hm=32b911757057d25f02e09d697c6e920a4e1fa9ff470e96227c378928c822f377&", "N/A", "Volume N/A"]))
                with yt_dlp.YoutubeDL(self.ydl_playlist_opts) as ydl:
                    listinfo = ydl.extract_info(linkModal.url, download=False)
                for entry in listinfo["entries"]:
                    self.queue.append(entry["url"])
                    title = entry["title"]
                    time = entry["duration"]
                    hours = time//3600
                    self.totalHours+=hours
                    time-=(hours*3600)
                    minutes = time//60
                    self.totalMinutes+=minutes
                    time-=(minutes*60)
                    self.totalSeconds+=time
                    timeString = f"{str(int(hours))+':' if int(hours) > 0 else ''}{str(int(minutes))+':' if int(minutes) > 0 else '0:'}{'0'+str(int(time)) if int(time) < 10 else str(int(time))}"
                    title_queue.append((title, False, False, timeString))
                if not self.vc.is_playing() and not self.paused:
                    self.interact = inter
                    await self.goNext()
                else:
                    self.queueButton.disabled = False
                    await inter.edit_original_response(embed=self.currembed, view=self)
            else:
                self.queue.append(linkModal.url)
                with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                    info = ydl.extract_info(linkModal.url, download=False)
                    title = info["title"]
                    time = info["duration_string"]
                    title_queue.append((title, False, False, time))
                    thumb = info["thumbnail"]
                await inter.edit_original_response(embed=await self.genEmbed([f"{title} has been Added to Queue", thumb, "Loading Video...", "Volume N/A"]))
                await asyncio.sleep(1)
                if not self.vc.is_playing() and not self.paused:
                    self.interact = inter
                    await self.goNext()
                else:
                    self.queueButton.disabled = False
                    await inter.edit_original_response(embed=self.currembed, view=self)
        else:
            await inter.response.send_message("CANT CLICK THE BUTTONS IF YOU'RE NOT IN A VC", ephemeral=True)

    async def playNext(self, inter: Interaction, fromSkip: bool = False):
        if not fromSkip:
            await inter.message.edit(embed=await self.genEmbed(["Grabbing Latest Video From Queue...", "https://cdn.discordapp.com/attachments/1267870147394277438/1268695496915025920/loading7_green.gif?ex=66ad5c41&is=66ac0ac1&hm=32b911757057d25f02e09d697c6e920a4e1fa9ff470e96227c378928c822f377&", "Loading Video...", "Volume N/A"]))
        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            info = ydl.extract_info(self.url, download=False)
            url2 = info['url']
            title = info["title"]
            thumbnail = info['thumbnail']
            duration = info["duration_string"]
            link = info["original_url"]
            self.currembed = await self.genEmbed([title, thumbnail, duration, link, int(float(self.volume)*100)])
            if self.queueButton is not None:
                self.queueButton.disabled = False
            await inter.message.edit(embed=self.currembed, view=self)
            source = discord.FFmpegPCMAudio(url2, **self.FFMPEG_OPTIONS)
            if not self.vc.is_playing():
                self.vc.play(source, after=self.afterFunc)
                self.vc.source = AudioSourceTracked(self.vc.source, self.volume)

    def afterFunc(self, error: Exception):
        try:
            self.songHist.append((self.url, title_queue[0]))
            print(self.songHist.lst)
            coro = self.goNext()
            fut = asyncio.run_coroutine_threadsafe(coro, client.loop)
            fut.result()
        except Exception as e:
            import traceback
            print(traceback.format_exception(e))
    
    async def goNext(self):
        try:
            if not self.loopOne and not self.prev:
                if self.looping:
                    self.queue.append(self.url)
                self.url = self.queue.pop(0)
                try:
                    if self.looping:
                        popped = title_queue.pop(0)
                        title_queue[0] = (title_queue[0][0], False, True, title_queue[0][3])
                        popped = (popped[0], False, False, popped[3])
                        title_queue.append(popped)
                    else:
                        if not self.first:
                            title_queue.pop(0)
                        else:
                            self.first = False
                except IndexError:
                    pass
                if self.vc.source is not None:
                    self.vc.source.cleanup()
                await self.playNext(self.interact, False)
            elif self.prev and not self.loopOne:
                if len(self.songHist.lst) == 1:
                    self.songHist.append((self.url, title_queue[0]))
                self.prev = False
                currSong = self.songHist.pop()
                prevSong = self.songHist.pop()
                self.queue.insert(0, currSong[0])
                self.queue.insert(0, prevSong[0])
                title_queue.insert(0, prevSong[1])
                if self.looping:
                    title_queue[0] = (title_queue[0][0], False, True, title_queue[0][3])
                else:
                    title_queue[0] = (title_queue[0][0], False, False, title_queue[0][3])
                title_queue[1] = (title_queue[1][0], False, False, title_queue[1][3])
                if self.vc.source is not None:
                    self.vc.source.cleanup()
                self.url = self.queue.pop(0)
                await self.playNext(self.interact, False)
            else:
                if self.vc.source is not None:
                    self.vc.source.cleanup()
                await self.playNext(self.interact, False)
        except IndexError:
            title_queue.clear()
            self.first = True
            await self.interact.message.edit(embed=await self.genEmbed(["Queue is Empty!", "https://cdn.discordapp.com/attachments/1267870147394277438/1268237425474539722/Porkfather.png?ex=66abb1a4&is=66aa6024&hm=3dc314686cee3a7008e2774629ef158fcdd4fb6b7cb9088a675e317e3131374f&", "No Video Loaded", "Volume N/A"]))

    @button(emoji=u"\U0001F501", row=1, custom_id="loopQueue")
    async def loop(self, inter: Interaction, button: Button):
        if inter.user.voice is not None and inter.user.voice.channel.id == self.vc.channel.id:
            if self.vc.is_playing():
                self.loopOne = False
                if not self.looping:
                    self.looping = True
                    title_queue[0] = (title_queue[0][0], False, True, title_queue[0][3])
                    await inter.response.send_message("Looping Song Queue", delete_after=2)
                else:
                    title_queue[0] = (title_queue[0][0], False, False, title_queue[0][3])
                    self.looping = False
                    await inter.response.send_message("Stopping the Song Loop", delete_after=2)
            else:
                await inter.response.send_message("Nothing is playing!", delete_after=2)
        else:
            await inter.response.send_message("CANT CLICK THE BUTTONS IF YOU'RE NOT IN A VC", ephemeral=True)

    @button(emoji="⏮", row=1, custom_id="prev")
    async def goBack(self, inter: Interaction, button: Button):
        if inter.user.voice is not None and inter.user.voice.channel.id == self.vc.channel.id:
            print(inter.user.display_name)
            if len(self.songHist.lst) >= 1:
                self.prev = True
                if self.vc.is_playing():
                    self.vc.stop()
                    await inter.response.send_message("Loading Previous Song...", delete_after=2)
                    await asyncio.sleep(1)
                else:
                    await inter.response.send_message("Queue is Empty!", delete_after=2)
            else:
                print(self.songHist.lst)
                await inter.response.send_message("There are no songs to go back to!", delete_after=2)
        else:
            await inter.response.send_message("CANT CLICK THE BUTTONS IF YOU'RE NOT IN A VC", ephemeral=True)

    @button(emoji="⏯", custom_id="pause", row=1)
    async def pause(self, inter: Interaction, button: Button):
        print(inter.user.display_name)
        if inter.user.voice is not None and inter.user.voice.channel.id == self.vc.channel.id:
            if not self.paused:
                self.vc.pause()
                self.paused = True
                await inter.response.send_message("Music Paused", delete_after=1)
            else:
                self.vc.resume()
                self.paused = False
                await inter.response.send_message("Music Resumed", delete_after=1)
        else:
            await inter.response.send_message("CANT CLICK THE BUTTONS IF YOU'RE NOT IN A VC", ephemeral=True)

    @button(emoji="⏭", row=1, custom_id="next")
    async def skip(self, inter: Interaction, button: Button):
        print(inter.user.display_name)
        if inter.user.voice is not None and inter.user.voice.channel.id == self.vc.channel.id:
            if self.vc.is_playing():
                self.vc.stop()
            await inter.response.send_message("Skipping Song...", delete_after=2)
            await asyncio.sleep(2)
        else:
            await inter.response.send_message("CANT CLICK THE BUTTONS IF YOU'RE NOT IN A VC", ephemeral=True)


    @button(emoji="⏹", custom_id="stop", row=2)
    async def stopSongs(self, inter: Interaction, button: Button):
        print(inter.user.display_name)
        if (inter.user.voice is not None and inter.user.voice.channel.id == self.vc.channel.id) or self.paused:
            try:
                self.queue.clear()
                title_queue.clear()
                self.songHist.clear()
                if self.vc.is_playing():
                    self.vc.stop()
                if self.looping:
                    self.looping = False
                if self.loopOne:
                    self.loopOne = False
                await inter.response.send_message("Queue Cleared!", delete_after=2)
            except Exception:
                await inter.response.send_message("Unable to Clear Queue.", delete_after=2)
        else:
            await inter.response.send_message("CANT CLICK THE BUTTONS IF YOU'RE NOT IN A VC", ephemeral=True)
    
    
            
    @button(emoji=u"\U0001F502", row=1, custom_id="loopOne")
    async def loopOneSong(self, inter: Interaction, button: Button):
        if inter.user.voice is not None and inter.user.voice.channel.id == self.vc.channel.id:
            if self.vc.is_playing():
                self.looping = False
                if not self.loopOne:
                    self.loopOne = True
                    title_queue[0] = (title_queue[0][0], True, False, title_queue[0][3])
                    await inter.response.send_message("Looping Current Song", delete_after=2)
                else:
                    title_queue[0] = (title_queue[0][0], False, False, title_queue[0][3])
                    self.loopOne = False
                    await inter.response.send_message("Stopping the Song Loop", delete_after=2)
            else:
                await inter.response.send_message("Nothing is playing!", delete_after=2)
        else:
            await inter.response.send_message("CANT CLICK THE BUTTONS IF YOU'RE NOT IN A VC", ephemeral=True)
        
    @button(emoji=u"\U0001F5C3", row=2, custom_id="getQueue")
    async def getQueue(self, inter:Interaction, button:Button):
        bullet_list = sorted([f"**{title_queue.index(title)+1}.** {title[0]}: {self.vc.source.progress} / {title[3]}" if title_queue.index(title) == 0 else f"**{title_queue.index(title)+1}.** {title[0]}: {title[3]}" for title in title_queue], key=lambda x: int(x[2:x.index(".")]))
        queue_name = f"Current Song Queue"
        if len(title_queue) > 0 and title_queue[0][1]:
            bullet_list[0] = f"**Currently Looping:** {bullet_list[0][bullet_list[0].index('.**')+3:]}"
        elif len(title_queue) > 0 and title_queue[0][2]:
            queue_name = "***Currently Looping Entire Queue:***"
        bullet_list.insert(0, f"Total Queue Time: {str(int(self.totalHours))+':' if int(self.totalHours) > 0 else ''}{str(int(self.totalMinutes))+':' if int(self.totalMinutes) > 0 else '0:'}{'0'+str(int(self.totalSeconds)) if int(self.totalSeconds) < 10 else str(int(self.totalSeconds))}")
        bullet_list = "\n".join(bullet_list) if len(bullet_list) > 0 else "Song Queue is Empty!"
        embedDict = {"color": int("4287f5", base=16), "title": queue_name, "description":bullet_list}
        embed = discord.Embed.from_dict(embedDict)
        await inter.response.send_message(embed=embed, delete_after=10)

    @button(emoji=u"\U0001F480", label="Die", row=2, custom_id="disconnect")
    async def die(self, inter: Interaction, button: Button):
        print(inter.user.display_name)
        if inter.user.voice is not None and inter.user.voice.channel.id == self.vc.channel.id:
            if not self.dead:
                if inter.guild.voice_client is not None:
                    self.queue.clear()
                    title_queue.clear()
                    self.songHist.clear()
                    self.dead = True
                    button.emoji = "❤"
                    button.label = "Live"
                    await inter.message.edit(view=self)
                    await inter.guild.voice_client.disconnect()
                    await inter.response.send_message("Died Successfully", delete_after=4)
                    await asyncio.sleep(4)
                else:
                    await inter.response.send_message("Did not Die Successfully", delete_after=4)
            else:
                if inter.guild.voice_client is None:
                    self.dead = False
                    button.emoji = u"\U0001F480"
                    button.label = "Die"
                    await inter.message.edit(view=self)
                    self.vc = await inter.user.voice.channel.connect()
                    await inter.response.send_message("Lived Successfully", delete_after=4)
                    await asyncio.sleep(4)
                else:
                    await inter.response.send_message("Did not Live Successfully", delete_after=4)
        else:
            await inter.response.send_message("CANT CLICK THE BUTTONS IF YOU'RE NOT IN A VC", ephemeral=True)

    @button(emoji=u"\U0001F50A", row=2, label="Volume Control", custom_id="volume")
    async def setVolume(self, inter:Interaction, button: Button):
        if inter.user.voice is not None and inter.user.voice.channel.id == self.vc.channel.id:
            volume = VolField(self.volume)
            await inter.response.send_modal(volume)
            button.disabled = True
            await inter.message.edit(view=self)
            timedout = await volume.wait()
            if timedout:
                button.disabled = False
                await inter.channel.send("You didnt put in a Volume in time!", delete_after=5)
                await inter.edit_original_response(embed=self.currembed, view=self)
            else:
                self.volume = volume.vol
                self.currembed.remove_field(2)
                self.currembed.insert_field_at(index=2, inline=True, name="Volume:", value=int(self.volume*100))
                button.disabled = False
                await inter.edit_original_response(embed=self.currembed, view=self)
                self.vc.source.volume = self.volume
        else:
            await inter.response.send_message("CANT CLICK THE BUTTONS IF YOU'RE NOT IN A VC", ephemeral=True)
    
    
        
    async def genEmbed(self, data):
        embed = {"color": int("4287f5", base=16), "title": "Media Player"}
        embed = discord.Embed.from_dict(embed)
        if isinstance(data[1], str):
            embed.set_thumbnail(url=data[1])
        try:
            link = f"[{data[0]}]({data[3]})"
            volume = data[4]
        except IndexError:
            link = data[0]
            volume = data[3]
        embed.insert_field_at(0, name="Currently Playing:", value=link)
        embed.insert_field_at(1, name="Duration:", value=data[2])
        embed.insert_field_at(2, name="Volume:", value=volume)
        return embed


@client.event
async def on_ready():
    await tree.sync(guild=guild)
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')


async def player(inter: Interaction):
    await inter.response.defer()
    if inter.user.voice is not None:
        vMembs = [member.id for member in inter.user.voice.channel.members]
        if 1211521026152865822 not in vMembs:
            vc = await inter.user.voice.channel.connect()
            embed = {"color": int("4287f5", base=16), "title": "Media Player"}
            embed = discord.Embed.from_dict(embed)
            embed.insert_field_at(0, name="Currently Playing:", value="Nothing...")
            embed.insert_field_at(1, name="Duration:", value="Duration N/A")
            embed.insert_field_at(2, name="Volume:", value="Volume N/A")
            embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1267870147394277438/1268237425474539722/Porkfather.png?ex=66abb1a4&is=66aa6024&hm=3dc314686cee3a7008e2774629ef158fcdd4fb6b7cb9088a675e317e3131374f&")
            global vidPlayer
            vidPlayer = Player(vc=vc, currEmbed=embed, timeout=3600)
            await inter.channel.purge(limit=10, check=lambda c: len(c.components) > 0 and c.author.id == 1211521026152865822)
            await inter.response.send_message(embed=embed, view=vidPlayer)
        elif 1211521026152865822 in vMembs:
            await inter.response.send_message("I'm already in the VC!", delete_after=2)
    else:
        await inter.response.send_message("You're not in a VC!", delete_after=2)

@tree.command(name="mediaplayer", description="Alias for /videoplayer")
async def mplay(inter: Interaction):
    await player(inter)
    
@tree.command(name="videoplayer", description="Start the videoplayer")
async def vplayer(inter: Interaction):
    await player(inter)

@tree.command(name="refresh", description="Resends the videoplayer embed")
async def resend(inter: Interaction):
    if inter.guild.voice_client is not None and inter.user.voice is not None:
        if inter.channel.id == client.cached_messages[-1].channel.id:
            for message in client.cached_messages[::-1]:
                if len(message.components) > 0:
                    embed = message.embeds[0]
                    delMessage = message
            await inter.response.send_message(embed=embed, view=vidPlayer)
            await inter.channel.delete_messages([delMessage])
            for message in client.cached_messages[::-1]:
                if len(message.components) > 0:
                    vidPlayer.interact.message = message
        else:
            await inter.response.send_message("You can only use this in the same channel where you originally used /videoplayer!")
            
    else:
        await inter.response.send_message("You cant use this if you dont have the player up and running!")
    
        

@tree.command(name="mycommand", description="Hi!")
async def hello(interaction: Interaction):
    await interaction.response.send_message(content="Hello World!")


@tree.command(name="nuke", description="Nukes the Server")
async def nuke(inter: Interaction):
    boom = discord.File(f"{os.getcwd()+os.sep}blowing-up-killed-the-toilet.gif", filename="boom.gif")
    colors = "123456789abcdef"
    color = "".join(choices(colors, k=6))
    embedContent = {"color": int(color, base=16),"title": "BOOOOOOOOOOOOOOOOOOOOOOOOOOOM!!!!!"}
    embed = discord.Embed.from_dict(embedContent)
    embed.set_image(url="attachment://boom.gif")
    await inter.response.send_message(embed=embed, file=boom)


@tree.command(name="dog", description="Dog go boom")
async def dog(inter: Interaction):
    boom = discord.File(f"{os.getcwd()+os.sep}dog_go_boom.mp4", filename="boom.mp4")
    await inter.response.send_message(file=boom)


@tree.command(name="warn", description="warn people (the funny)")
async def warn(inter: Interaction, user: discord.member.Member, message: str):
    if inter.user.top_role.id in [732721267115032747, 1267870834416947262]:
        guild = client.get_guild(727745299614793728)
        channels = inter.guild.channels
        channelNames = [a.name for a in channels]
        if f"{user.display_name.lower()}-warning-channel" in channelNames:
            channel = channels[channelNames.index(f"{user.display_name.lower()}-warning-channel")]
        else:
            channel = await inter.guild.create_text_channel(f"{user.display_name} WARNING CHANNEL", overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False), user: discord.PermissionOverwrite(view_channel=True, send_messages=False)})
        await channel.send(f"{user.mention}, you have been warned because of: {message}")
        await inter.response.send_message(embed=discord.Embed(color=int("42f54e", base=16), title=f"✅ *{user.display_name} has been warned*"))
        await asyncio.sleep(600)
        await channel.delete()
    else:
        await inter.response.send_message("YOU CANT USE THIS COMMAND!!! CRY ABOUT IT!!!!", ephemeral=True)


@tree.command(name="kicks", description="Pumped Up fr fr")
async def kicks(inter: Interaction):
    if inter.guild.voice_client is not None:
        await inter.guild.voice_client.disconnect()
    channel = await inter.user.voice.channel.connect()
    coro = disconnect(channel)
    channel.play(discord.FFmpegPCMAudio("ALDIODER KIDS.mp3"), after=lambda e: asyncio.run_coroutine_threadsafe(coro, client.loop))
    await inter.response.send_message("ALDIODER KIDS", delete_after=5)


@tree.command(name="gedagedigedagedo", description="Funny Chicken Nugget")
async def nugget(inter: Interaction):
    if inter.guild.voice_client is not None:
        await inter.guild.voice_client.disconnect()
    channel = await inter.user.voice.channel.connect()
    coro = disconnect(channel)
    channel.play(discord.FFmpegPCMAudio("gedagedigedagedago.mp3"), after=lambda e: asyncio.run_coroutine_threadsafe(coro, client.loop))
    await inter.response.send_message("Gedagedigedagedo".upper(), delete_after=5)


@tree.command(name="rock", description="Throws a Rock")
async def throw(inter: Interaction):
    boom = discord.File(f"{os.getcwd()+os.sep}rapidsave.com_guy_wraps_rock_in_copper_wire_and_throws_it_at-a84x7eer4ro81.mp4", filename="boom.mp4")
    await inter.response.send_message(file=boom)

@tree.command(name="play_file", description="Play music from a file")
async def playFile(inter: Interaction, file: discord.Attachment):
    if inter.guild.voice_client is not None:
        await inter.response.send_message("You cant use this command when I'm already in a VC!")
    else:
        channel = await inter.user.voice.channel.connect()
        coro = disconnect(channel, inter)
        url = file.url
        if file.filename[file.filename.rindex("."):] in [".mp4", ".mp3", ".wav", ".ogg", ".mov"]:
            source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
            channel.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(coro, client.loop))
            embedDict = {"color":int("03ecfc", base=16), "title": "Now Playing:", "description": f"{file.filename[:file.filename.rindex('.')]}"}
            embed = discord.Embed.from_dict(embedDict)
            embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1267870147394277438/1268237425474539722/Porkfather.png?ex=66abb1a4&is=66aa6024&hm=3dc314686cee3a7008e2774629ef158fcdd4fb6b7cb9088a675e317e3131374f&")
            await inter.response.send_message(embed=embed)
        else:
            await inter.response.send_message(f"Invalid File!", delete_after=5)
        

@tree.command(name="thanos", description="Perfectly Balanced. As all things should be")
async def thanos(inter: Interaction):
    if inter.user.id == 727609947470299257:
        membs = list(inter.guild.members)
        shuffle(membs)
        membs = [item for item in membs if item.id != 727609947470299257 and item.id != 310953543395966977 and item.id != 168058822114541570 and item.id != 812049779528826910]
        membLen = len(membs)//2
        membs = membs[:membLen]
        await inter.response.send_message("THANOS'D SUCCESSFULLY")
        for member in membs:
            try:
                await member.send("YOU'VE BEEN THANOS'D BY THE PORKFATHER")
            except Exception:
                pass
            try:
                await inter.guild.ban(user=member, reason="YOU'VE BEEN THANOS'D BY THE PORKFATHER")
            except Exception:
                pass
            try:
                await inter.guild.unban(user=member, reason="YOU'VE BEEN GRACED BY THE FATHER OF PORK")
            except Exception:
                pass
            try:
                await member.send("https://discord.gg/KgKSe4DY32")
            except Exception:
                pass
    else:
        await inter.response.send_message("Not Wallman", delete_after=5)


@tree.command(name="bible", description="The Bald Bible")
async def bible(inter: Interaction):
    await inter.response.send_message(content="https://tenor.com/view/tf2-bald-engineer-bec-2fort-gif-22082556")
        
async def disconnect(channel:discord.VoiceClient, inter: Interaction = None):
    await asyncio.sleep(0.5)
    await channel.disconnect()
    if inter is not None:
        await inter.delete_original_response()
with open("auth.txt") as key:
    keyStr = key.readline().strip()
    client.run(keyStr)