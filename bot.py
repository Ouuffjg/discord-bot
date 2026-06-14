import discord
from discord.ext import commands
from discord import app_commands
import asyncio, json, os, random, urllib.parse, aiohttp
from datetime import datetime, timedelta

CONFIG_FILE = 'ticket_config.json'
SECURITY_FILE = 'security_config.json'
ANTIRAID_FILE = 'antiraid_config.json'
SUGGEST_FILE = 'suggest_config.json'
WARNINGS_FILE = 'warnings.json'
INVITE_FILE = 'invite_config.json'
open_tickets = {}
waiting_mention = {}
anti_raid_enabled = {}
invite_tracker = {}
afk_users = {}
polls = {}
giveaways = {}
invite_tracking = {}
maintenance_mode = False
BOT_OWNER_ID = 1291450569113862176

def load_json(file):
    if os.path.exists(file):
        with open(file, 'r', encoding='utf-8') as f: return json.load(f)
    return {}

def save_json(file, data):
    with open(file, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

def parse_duration(d):
    d = d.lower().strip()
    if d in ['permanent','forever','perm']: return None
    v=''; u=''
    for c in d:
        if c.isdigit(): v+=c
        else: u+=c
    if not v: return None
    v=int(v)
    if u in ['s','sec']: return timedelta(seconds=v)
    elif u in ['m','min']: return timedelta(minutes=v)
    elif u in ['h','hr']: return timedelta(hours=v)
    elif u in ['d','day']: return timedelta(days=v)
    elif u in ['w','week']: return timedelta(weeks=v)
    elif u in ['mm','month']: return timedelta(days=v*30)
    elif u in ['a','y','year']: return timedelta(days=v*365)
    else: return None

def format_duration(td):
    if td is None: return "Permanent"
    d=td.days; h=td.seconds//3600; m=(td.seconds%3600)//60; s=td.seconds%60
    p=[]
    if d>0: p.append(f"{d}d")
    if h>0: p.append(f"{h}h")
    if m>0: p.append(f"{m}m")
    if s>0 or not p: p.append(f"{s}s")
    return " ".join(p)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.idle)
    try: s=await bot.tree.sync(); print(f'[SYNC] {len(s)} commands')
    except Exception as e: print(f'[SYNC ERROR] {e}')
    await asyncio.sleep(10)
    try: s=await bot.tree.sync(); print(f'[SYNC2] {len(s)} commands')
    except: pass
    ac=load_json(ANTIRAID_FILE)
    for gid,cfg in ac.items(): anti_raid_enabled[int(gid)]=cfg.get('enabled',False)
    config=load_json(CONFIG_FILE)
    for gid,cfg in config.items():
        ch_id=cfg.get('panel_channel_id')
        if not ch_id: continue
        g=bot.get_guild(int(gid))
        if not g: continue
        ch=g.get_channel(int(ch_id))
        if not ch: continue
        mid=cfg.get('panel_msg_id')
        if mid:
            try: old=await ch.fetch_message(int(mid)); await old.delete()
            except: pass
        try:
            c=int(cfg.get('embed_color','#FFA500').replace('#',''),16)
            embed=discord.Embed(title=cfg.get('embed_title_open','Ticket System'),description=cfg.get('embed_desc_open','Click the button below to open a ticket!'),color=c)
            embed.set_footer(text=cfg.get('embed_footer_open','Click the button below'))
            nm=await ch.send(embed=embed,view=TicketView(cfg))
            cfg['panel_msg_id']=nm.id; save_json(CONFIG_FILE,config)
            print(f'[OK] Panel in {g.name}')
        except Exception as e: print(f'[ERROR] {e}')
    ic=load_json(INVITE_FILE)
    for gid,cfg in ic.items():
        if cfg.get('enabled'):
            g=bot.get_guild(int(gid))
            if g:
                try:
                    invs=await g.invites()
                    for inv in invs: invite_tracking[inv.code]={'inviter':inv.inviter.id if inv.inviter else None,'uses':inv.uses}
                except: pass
    print(f'Bot ready! {bot.user}')

@bot.event
async def on_member_join(member):
    gid=member.guild.id
    if anti_raid_enabled.get(gid,False) and member.bot:
        try:
            await member.kick(reason='Anti-raid')
            try:
                async for e in member.guild.audit_logs(action=discord.AuditLogAction.bot_add,limit=1):
                    if e.target.id==member.id:
                        inv=e.user
                        if inv and inv.top_role<member.guild.me.top_role:
                            for r in [r for r in inv.roles if r!=member.guild.default_role]:
                                try: await inv.remove_roles(r,reason='Anti-raid')
                                except: pass
                        break
            except: pass
            await send_antiraid_log(member.guild,'bot_kick',member)
        except: pass
        return
    config=load_json(INVITE_FILE); gs=str(gid)
    if gs in config and config[gs].get('enabled'):
        try:
            ni=await member.guild.invites()
            for inv in ni:
                if inv.code in invite_tracking:
                    ou=invite_tracking[inv.code]['uses']
                    if inv.uses>ou:
                        iid=invite_tracking[inv.code]['inviter']
                        invite_tracking[inv.code]['uses']=inv.uses
                        age=(datetime.now().astimezone()-member.created_at).days
                        fake=age<7
                        if 'invites' not in config[gs]: config[gs]['invites']={}
                        istr=str(iid)
                        if istr not in config[gs]['invites']: config[gs]['invites'][istr]={'real':0,'fake':0,'left':0}
                        if fake: config[gs]['invites'][istr]['fake']+=1
                        else: config[gs]['invites'][istr]['real']+=1
                        save_json(INVITE_FILE,config)
                        lc=config[gs].get('log_channel')
                        if lc:
                            lch=member.guild.get_channel(int(lc))
                            if lch:
                                inviter=member.guild.get_member(iid)
                                embed=discord.Embed(title='New Member',description=f'{member.mention} joined!',color=discord.Color.green() if not fake else discord.Color.orange(),timestamp=datetime.now())
                                embed.add_field(name='Invited by',value=inviter.mention if inviter else f'ID: {iid}',inline=True)
                                embed.add_field(name='Type',value='Real' if not fake else 'Alt/Fake (<7 days)',inline=True)
                                embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
                                await lch.send(embed=embed)
                        break
        except: pass

@bot.event
async def on_member_remove(member):
    config=load_json(INVITE_FILE); gs=str(member.guild.id)
    if gs not in config or not config[gs].get('enabled'): return
    uid=str(member.id)
    if 'left_users' not in config[gs]: config[gs]['left_users']={}
    config[gs]['left_users'][uid]={'name':member.name,'left_at':datetime.now().strftime('%m/%d/%Y at %H:%M')}
    save_json(INVITE_FILE,config)

@bot.event
async def on_message(message):
    if message.author.bot: return
    cid=str(message.channel.id)
    if message.author.id in afk_users:
        del afk_users[message.author.id]
        try: await message.author.edit(nick=message.author.display_name.replace('[AFK] ',''))
        except: pass
        await message.channel.send(f'Welcome back {message.author.mention}!',delete_after=5)
    if message.mentions:
        for u in message.mentions:
            if u.id in afk_users:
                a=afk_users[u.id]; t=datetime.now()-a['time']
                h,rem=divmod(t.seconds,3600); m,s=divmod(rem,60)
                ts=f'{h}h {m}m {s}s' if h>0 else f'{m}m {s}s'
                await message.channel.send(f'{u.mention} is AFK: {a["reason"]} ({ts})',delete_after=10)
    if message.guild and anti_raid_enabled.get(message.guild.id,False):
        if 'discord.gg/' in message.content or 'discord.com/invite/' in message.content:
            await message.delete()
            uid=message.author.id; gid=message.guild.id
            if gid not in invite_tracker: invite_tracker[gid]={}
            if uid not in invite_tracker[gid]: invite_tracker[gid][uid]=[]
            invite_tracker[gid][uid].append(datetime.now())
            recent=[t for t in invite_tracker[gid][uid] if (datetime.now()-t).total_seconds()<18000]
            invite_tracker[gid][uid]=recent
            if len(recent)>=2:
                try: await message.author.timeout(timedelta(hours=3),reason='Invites')
                except: pass
                try:
                    embed=discord.Embed(title='Warning',description=f'You have been warned in **{message.guild.name}**',color=discord.Color.yellow())
                    embed.add_field(name='Reason',value='Sending invites multiple times',inline=True)
                    embed.add_field(name='Duration',value='3h mute + Warning',inline=True)
                    await message.author.send(embed=embed)
                except: pass
                await message.channel.send(f'{message.author.mention}, muted for 3h.',delete_after=10)
            else: await message.channel.send(f'{message.author.mention}, do not send invites.',delete_after=5)
            return
    if cid in waiting_mention:
        info=waiting_mention[cid]
        if message.author.id==info['author_id'] and message.mentions:
            m=message.mentions[0]
            if info['action']=='add':
                await message.channel.set_permissions(m,read_messages=True,send_messages=True)
                await message.channel.send(f'{m.mention} added!',delete_after=5)
            else:
                await message.channel.set_permissions(m,overwrite=None)
                await message.channel.send(f'{m.mention} removed!',delete_after=5)
            await message.delete(); del waiting_mention[cid]
        elif message.author.id==info['author_id']:
            await message.delete(); await message.channel.send('Mention a user!',delete_after=3)
        return
    if cid in open_tickets:
        t=open_tickets[cid]; uid=t['user_id']; cb=t.get('claimed_by')
        config=load_json(CONFIG_FILE)
        rids=config.get(str(message.guild.id),{}).get('staff_role_ids',[])
        urs=[r.id for r in message.author.roles]
        is_staff=message.author.id==BOT_OWNER_ID or any(rid in urs for rid in rids) or message.author.guild_permissions.administrator
        if cb is None and is_staff and message.author.id!=uid:
            open_tickets[cid]['claimed_by']=message.author.id
            await message.channel.set_permissions(message.author,read_messages=True,send_messages=True)
            await message.channel.send(f'Claimed by {message.author.mention}',delete_after=10)
        if cb is None:
            if not is_staff and message.author.id!=uid: await message.delete()
        else:
            if message.author.id not in [uid,cb] and not is_staff: await message.delete()

async def send_antiraid_log(guild,action,target):
    c=load_json(ANTIRAID_FILE); gs=str(guild.id)
    if gs not in c: return
    lc=c[gs].get('log_channel')
    if not lc: return
    lch=guild.get_channel(int(lc))
    if not lch: return
    embed=discord.Embed(title='Anti-Raid',description=f'**Action:** {action}\n**Target:** {target.name} ({target.id})',color=discord.Color.red(),timestamp=datetime.now())
    await lch.send(embed=embed)

async def send_security_log(guild,action,moderator,target,reason,duration):
    c=load_json(SECURITY_FILE); gs=str(guild.id)
    if gs not in c: return
    lc=c[gs].get('log_channel')
    if not lc: return
    lch=guild.get_channel(int(lc))
    if not lch: return
    colors={'ban':discord.Color.red(),'hackban':discord.Color.dark_red(),'mute':discord.Color.orange(),'warn':discord.Color.yellow()}
    embed=discord.Embed(title=f'{action.title()} | Case',color=colors.get(action,discord.Color.orange()),timestamp=datetime.now())
    embed.add_field(name='Moderator',value=moderator.mention,inline=True)
    if isinstance(target,(discord.Member,discord.User)): embed.add_field(name='User',value=f'{target.mention} ({target.id})',inline=True)
    else: embed.add_field(name='User ID',value=str(target),inline=True)
    embed.add_field(name='Reason',value=reason,inline=False)
    if duration: embed.add_field(name='Duration',value=duration,inline=True)
    view=None
    if action in ['ban','hackban']: view=UnbanView(target.id if isinstance(target,(discord.Member,discord.User)) else target,guild.id)
    await lch.send(embed=embed,view=view)

class UnbanView(discord.ui.View):
    def __init__(self,uid,gid): super().__init__(timeout=None); self.uid=uid; self.gid=gid
    @discord.ui.button(label='Remove Ban',style=discord.ButtonStyle.green)
    async def unban(self,i,b):
        if i.user.id!=BOT_OWNER_ID and not i.user.guild_permissions.ban_members: await i.response.send_message('No permission!',ephemeral=True); return
        g=bot.get_guild(self.gid)
        if not g: await i.response.send_message('Guild not found!',ephemeral=True); return
        try: await g.unban(discord.Object(id=self.uid)); await i.response.send_message('Ban removed!',ephemeral=True); b.disabled=True; await i.message.edit(view=self)
        except Exception as e: await i.response.send_message(f'Error: {e}',ephemeral=True)

async def save_logs(channel,who):
    try:
        c=load_json(CONFIG_FILE); g=str(channel.guild.id)
        if g not in c: return
        lc=c[g].get('log_channel_id')
        if not lc: return
        lch=channel.guild.get_channel(int(lc))
        if not lch: return
        info=open_tickets.get(str(channel.id),{})
        oa=info.get('created_at',datetime.now()); ca=datetime.now()
        dur=ca-oa; h,rem=divmod(dur.seconds,3600); m,s=divmod(rem,60)
        ds=f'{dur.days}d {h}h {m}m {s}s' if dur.days>0 else f'{h}h {m}m {s}s' if h>0 else f'{m}m {s}s' if m>0 else f'{s}s'
        embed=discord.Embed(title='Ticket Closed',description=f'**Channel:** `{channel.name}`',color=discord.Color.orange(),timestamp=ca)
        embed.add_field(name='Opened by',value=f'<@{info.get("user_id","?")}>',inline=True)
        embed.add_field(name='Closed by',value=f'{who.mention}',inline=True)
        if info.get('claimed_by'):
            cu=channel.guild.get_member(info['claimed_by'])
            embed.add_field(name='Claimed by',value=cu.mention if cu else 'Unknown',inline=True)
        embed.add_field(name='Duration',value=ds,inline=True)
        embed.add_field(name='Opened',value=oa.strftime('%m/%d/%Y %H:%M'),inline=True)
        embed.add_field(name='Closed',value=ca.strftime('%m/%d/%Y %H:%M'),inline=True)
        await lch.send(embed=embed)
    except: pass
@bot.tree.command(name='lock', description='Lock a channel')
@app_commands.describe(channel='Channel to lock')
async def lock(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.manage_channels: await interaction.response.send_message('No permission!', ephemeral=True); return
    if channel is None: channel = interaction.channel
    await channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await interaction.response.send_message(f'{channel.mention} locked.')

@bot.tree.command(name='unlock', description='Unlock a channel')
@app_commands.describe(channel='Channel to unlock')
async def unlock(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.manage_channels: await interaction.response.send_message('No permission!', ephemeral=True); return
    if channel is None: channel = interaction.channel
    await channel.set_permissions(interaction.guild.default_role, send_messages=None)
    await interaction.response.send_message(f'{channel.mention} unlocked.')

@bot.tree.command(name='purge', description='Delete messages')
@app_commands.describe(amount='Number (1-100)')
async def purge(interaction: discord.Interaction, amount: int):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.manage_messages: await interaction.response.send_message('No permission!', ephemeral=True); return
    if amount < 1 or amount > 100: await interaction.response.send_message('1-100!', ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f'{len(deleted)} messages deleted.', ephemeral=True)
@bot.tree.command(name='nickname', description='Change nickname')
@app_commands.describe(member='Member', nickname='New nickname')
async def nickname(interaction: discord.Interaction, member: discord.Member, nickname: str):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.manage_nicknames: await interaction.response.send_message('No permission!', ephemeral=True); return
    if member.top_role >= interaction.user.top_role and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Cannot!', ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    await member.edit(nick=nickname)
    await interaction.followup.send(f'Nickname changed to **{nickname}**.', ephemeral=True)

@bot.tree.command(name='role', description='Add or remove a role')
@app_commands.describe(action='Add or remove', member='Member', role='Role')
@app_commands.choices(action=[app_commands.Choice(name='Add', value='add'), app_commands.Choice(name='Remove', value='remove')])
async def role(interaction: discord.Interaction, action: app_commands.Choice[str], member: discord.Member, role: discord.Role):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.manage_roles: await interaction.response.send_message('No permission!', ephemeral=True); return
    if role.position >= interaction.user.top_role.position and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Cannot!', ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    if action.value == 'add': await member.add_roles(role); await interaction.followup.send(f'{role.mention} added to {member.mention}.')
    else: await member.remove_roles(role); await interaction.followup.send(f'{role.mention} removed from {member.mention}.')

@bot.tree.command(name='massrole', description='Add role to multiple members')
@app_commands.describe(role='Role', members='Mentions (space separated)')
async def massrole(interaction: discord.Interaction, role: discord.Role, members: str):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.manage_roles: await interaction.response.send_message('No permission!', ephemeral=True); return
    member_ids = []
    for w in members.split():
        w = w.strip().replace('<@','').replace('>','').replace('!','')
        try: member_ids.append(int(w))
        except: pass
    if not member_ids: await interaction.response.send_message('No valid members!', ephemeral=True); return
    added = []
    for mid in member_ids:
        m = interaction.guild.get_member(mid)
        if m:
            try: await m.add_roles(role); added.append(m.mention)
            except: pass
    await interaction.response.send_message(f'{role.mention} added to {len(added)} members.')
@bot.tree.command(name='afk', description='Set AFK status')
@app_commands.describe(reason='Reason')
async def afk(interaction: discord.Interaction, reason: str):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    afk_users[interaction.user.id] = {'reason': reason, 'time': datetime.now()}
    try: await interaction.user.edit(nick=f'[AFK] {interaction.user.display_name}')
    except: pass
    await interaction.response.send_message(f'{interaction.user.mention} is now AFK. Reason: {reason}')
@bot.tree.command(name='warn', description='Warn a member')
@app_commands.describe(member='Member', reason='Reason')
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.moderate_members: await interaction.response.send_message('No permission!', ephemeral=True); return
    try:
        embed=discord.Embed(title='Warning',description=f'You have been warned in **{interaction.guild.name}**',color=discord.Color.yellow())
        embed.add_field(name='Reason',value=reason,inline=True)
        await member.send(embed=embed)
    except: pass
    c=load_json(WARNINGS_FILE); g=str(interaction.guild.id); u=str(member.id)
    if g not in c: c[g]={}
    if u not in c[g]: c[g][u]=[]
    c[g][u].append({'reason':reason,'date':datetime.now().strftime('%m/%d/%Y at %H:%M'),'moderator':interaction.user.id})
    save_json(WARNINGS_FILE,c)
    await interaction.response.send_message(f'{member.mention} has been warned. Reason: {reason}')
    await send_security_log(interaction.guild,'warn',interaction.user,member,reason,'N/A')

@bot.tree.command(name='warnings', description='View warnings')
@app_commands.describe(user='User')
async def warnings(interaction: discord.Interaction, user: discord.Member):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.moderate_members: await interaction.response.send_message('No permission!', ephemeral=True); return
    c=load_json(WARNINGS_FILE); g=str(interaction.guild.id); u=str(user.id)
    if g not in c or u not in c[g]: await interaction.response.send_message(f'{user.mention} has no warnings.',ephemeral=True); return
    warns=c[g][u]
    embed=discord.Embed(title=f'Warnings for {user.name}',color=discord.Color.orange(),timestamp=datetime.now())
    embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
    for i,w in enumerate(warns[:10],1): embed.add_field(name=f'Warning #{i}',value=f'**Reason:** {w["reason"]}\n**Date:** {w["date"]}\n**By:** <@{w["moderator"]}>',inline=False)
    embed.set_footer(text=f'Total: {len(warns)}')
    await interaction.response.send_message(embed=embed,ephemeral=True)

@bot.tree.command(name='clearwarn', description='Remove a warning')
@app_commands.describe(user='User', warning_number='Warning number')
async def clearwarn(interaction: discord.Interaction, user: discord.Member, warning_number: int):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.moderate_members: await interaction.response.send_message('No permission!', ephemeral=True); return
    c=load_json(WARNINGS_FILE); g=str(interaction.guild.id); u=str(user.id)
    if g not in c or u not in c[g]: await interaction.response.send_message(f'{user.mention} has no warnings.',ephemeral=True); return
    warns=c[g][u]
    if warning_number<1 or warning_number>len(warns): await interaction.response.send_message(f'Invalid! 1-{len(warns)}.',ephemeral=True); return
    removed=warns.pop(warning_number-1); save_json(WARNINGS_FILE,c)
    embed=discord.Embed(title='Warning Removed',color=discord.Color.orange(),timestamp=datetime.now())
    embed.add_field(name='User',value=user.mention,inline=True)
    embed.add_field(name='Removed',value=f'**Reason:** {removed["reason"]}\n**Date:** {removed["date"]}',inline=False)
    embed.add_field(name='Remaining',value=str(len(warns)),inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='reason', description='Update case reason')
@app_commands.describe(case_id='Case ID', new_reason='New reason')
async def reason(interaction: discord.Interaction, case_id: str, new_reason: str):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.moderate_members: await interaction.response.send_message('No permission!', ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    c=load_json(WARNINGS_FILE); g=str(interaction.guild.id)
    found=False
    if g in c:
        for u,warns in c[g].items():
            for i,w in enumerate(warns):
                if str(i+1)==case_id:
                    old=w['reason']; w['reason']=new_reason; w['updated']=True; w['updated_by']=interaction.user.id; w['updated_at']=datetime.now().strftime('%m/%d/%Y at %H:%M')
                    save_json(WARNINGS_FILE,c); found=True
                    sc=load_json(SECURITY_FILE)
                    if g in sc:
                        lc=sc[g].get('log_channel')
                        if lc:
                            lch=interaction.guild.get_channel(int(lc))
                            if lch:
                                embed=discord.Embed(title='Warning Updated',color=discord.Color.orange(),timestamp=datetime.now())
                                embed.add_field(name='User',value=f'<@{u}>',inline=True)
                                embed.add_field(name='Case',value=f'#{i+1}',inline=True)
                                embed.add_field(name='Updated by',value=interaction.user.mention,inline=True)
                                embed.add_field(name='Old',value=old,inline=False)
                                embed.add_field(name='New',value=new_reason,inline=False)
                                await lch.send(embed=embed)
                    await interaction.followup.send(f'Warning #{i+1} updated.\n**Old:** {old}\n**New:** {new_reason}')
                    break
            if found: break
    if not found: await interaction.followup.send('Case not found!',ephemeral=True)

@bot.tree.command(name='suggest', description='Send a suggestion')
@app_commands.describe(suggestion='Your suggestion')
async def suggest(interaction: discord.Interaction, suggestion: str):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    c=load_json(SUGGEST_FILE); g=str(interaction.guild.id)
    if g not in c or not c[g].get('channel_id'): await interaction.response.send_message('Not configured!',ephemeral=True); return
    ch=interaction.guild.get_channel(int(c[g]['channel_id']))
    if not ch: await interaction.response.send_message('Channel not found!',ephemeral=True); return
    embed=discord.Embed(title='New Suggestion',description=suggestion,color=discord.Color.orange(),timestamp=datetime.now())
    embed.set_author(name=interaction.user.name,icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
    embed.set_footer(text=f'ID: {interaction.user.id}')
    msg=await ch.send(embed=embed); await msg.add_reaction('✅'); await msg.add_reaction('❌')
    await interaction.response.send_message('Suggestion sent!',ephemeral=True)

@bot.tree.command(name='suggestconfig', description='Configure suggestion channel')
@app_commands.describe(channel='Channel')
async def suggestconfig(interaction: discord.Interaction, channel: discord.TextChannel):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.administrator: await interaction.response.send_message('No permission!',ephemeral=True); return
    c=load_json(SUGGEST_FILE); g=str(interaction.guild.id)
    if g not in c: c[g]={}
    c[g]['channel_id']=channel.id; save_json(SUGGEST_FILE,c)
    await interaction.response.send_message(f'Suggestion channel set to {channel.mention}',ephemeral=True)
@bot.tree.command(name='poll', description='Create a poll')
@app_commands.describe(channel='Channel', question='Question', duration='Duration (1h, 30m, 1d)', option1='Option 1', option2='Option 2', option3='Option 3', option4='Option 4', option5='Option 5')
async def poll(interaction: discord.Interaction, channel: discord.TextChannel, question: str, duration: str, option1: str, option2: str, option3: str = None, option4: str = None, option5: str = None):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.administrator: await interaction.response.send_message('No permission!', ephemeral=True); return
    td=parse_duration(duration)
    if td is None: await interaction.response.send_message('Invalid duration!', ephemeral=True); return
    options=[option1,option2]
    if option3: options.append(option3)
    if option4: options.append(option4)
    if option5: options.append(option5)
    emojis=['1️⃣','2️⃣','3️⃣','4️⃣','5️⃣']
    embed=discord.Embed(title='Poll',description=question,color=discord.Color.orange(),timestamp=datetime.now())
    embed.set_author(name=interaction.user.name,icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
    for i,opt in enumerate(options): embed.add_field(name=f'{emojis[i]} {opt}',value='\u200b',inline=False)
    embed.set_footer(text=f'Ends in {format_duration(td)}')
    msg=await channel.send(embed=embed)
    for i in range(len(options)): await msg.add_reaction(emojis[i])
    polls[msg.id]={'channel_id':channel.id,'end_time':datetime.now()+td}
    await interaction.response.send_message(f'Poll created in {channel.mention}!', ephemeral=True)
    await asyncio.sleep(td.total_seconds())
    try:
        msg=await channel.fetch_message(msg.id)
        results={}
        for r in msg.reactions:
            if str(r.emoji) in emojis[:len(options)]: results[str(r.emoji)]=r.count-1
        rembed=discord.Embed(title='Poll Results',description=question,color=discord.Color.orange(),timestamp=datetime.now())
        for i,opt in enumerate(options): rembed.add_field(name=f'{emojis[i]} {opt}',value=f'{results.get(emojis[i],0)} votes',inline=False)
        rembed.set_footer(text='Poll ended')
        await channel.send(embed=rembed)
    except: pass

@bot.tree.command(name='giveaway', description='Create a giveaway')
@app_commands.describe(channel='Channel', prize='Prize', duration='Duration (1h, 30m, 1d)', winners='Number of winners')
async def giveaway(interaction: discord.Interaction, channel: discord.TextChannel, prize: str, duration: str, winners: int):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.administrator: await interaction.response.send_message('No permission!', ephemeral=True); return
    if winners<1: await interaction.response.send_message('At least 1 winner!', ephemeral=True); return
    td=parse_duration(duration)
    if td is None: await interaction.response.send_message('Invalid duration!', ephemeral=True); return
    end_time=datetime.now()+td
    embed=discord.Embed(title='Giveaway',description=f'**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** <t:{int(end_time.timestamp())}:R>',color=discord.Color.orange(),timestamp=end_time)
    embed.set_footer(text='React with 🎉 to enter!')
    msg=await channel.send(embed=embed); await msg.add_reaction('🎉')
    giveaways[msg.id]={'channel_id':channel.id,'prize':prize,'winners':winners,'end_time':end_time}
    await interaction.response.send_message(f'Giveaway created in {channel.mention}!', ephemeral=True)
    await asyncio.sleep(td.total_seconds())
    try:
        msg=await channel.fetch_message(msg.id)
        for r in msg.reactions:
            if str(r.emoji)=='🎉':
                users=[u async for u in r.users() if not u.bot]
                aw=users if len(users)<winners else random.sample(users,winners)
                wt=' '.join([u.mention for u in aw])
                rembed=discord.Embed(title='Giveaway Ended',description=f'**Prize:** {prize}\n**Winners:** {wt}',color=discord.Color.orange(),timestamp=datetime.now())
                await channel.send(embed=rembed)
                await channel.send(f'Congratulations {wt}! You won **{prize}**!')
                break
    except: pass
@bot.tree.command(name='antiraid', description='Toggle anti-raid')
async def antiraid(interaction: discord.Interaction):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.administrator: await interaction.response.send_message('No permission!', ephemeral=True); return
    gid=interaction.guild.id; ac=load_json(ANTIRAID_FILE); gs=str(gid)
    if gs not in ac: ac[gs]={'enabled':False,'log_channel':None}
    if anti_raid_enabled.get(gid,False):
        anti_raid_enabled[gid]=False; ac[gs]['enabled']=False; save_json(ANTIRAID_FILE,ac)
        await interaction.response.send_message(embed=discord.Embed(title='Anti-Raid Disabled',color=discord.Color.red()))
    else:
        anti_raid_enabled[gid]=True; ac[gs]['enabled']=True; save_json(ANTIRAID_FILE,ac)
        embed=discord.Embed(title='Anti-Raid Enabled',color=discord.Color.green())
        lc=interaction.guild.get_channel(int(ac[gs]['log_channel'])) if ac[gs].get('log_channel') else None
        embed.add_field(name='Log Channel',value=lc.mention if lc else 'Not set')
        await interaction.response.send_message(embed=embed, view=AntiRaidConfigView())

class AntiRaidConfigView(discord.ui.View):
    def __init__(self): super().__init__(timeout=600)
    @discord.ui.button(label='Set Log Channel', style=discord.ButtonStyle.primary)
    async def set_logs(self, i, b): await i.response.send_modal(AntiRaidLogModal())

class AntiRaidLogModal(discord.ui.Modal, title='Set Anti-Raid Log'):
    channel_id = discord.ui.TextInput(label='Channel ID', placeholder='Paste the channel ID', required=True)
    async def on_submit(self, i):
        try:
            ch=i.guild.get_channel(int(self.channel_id.value))
            if ch:
                c=load_json(ANTIRAID_FILE); g=str(i.guild.id)
                if g not in c: c[g]={}
                c[g]['log_channel']=ch.id; save_json(ANTIRAID_FILE,c)
                await i.response.send_message(f'Log channel: {ch.mention}', ephemeral=True)
            else: await i.response.send_message('Not found!', ephemeral=True)
        except: await i.response.send_message('Invalid ID!', ephemeral=True)

@bot.tree.command(name='securitypanel', description='Configure security logs')
async def securitypanel(interaction: discord.Interaction):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.administrator: await interaction.response.send_message('No permission!', ephemeral=True); return
    c=load_json(SECURITY_FILE); g=str(interaction.guild.id)
    if g not in c: c[g]={'log_channel':None}; save_json(SECURITY_FILE,c)
    embed=discord.Embed(title='Security Configuration',color=discord.Color.orange())
    lc=interaction.guild.get_channel(int(c[g]['log_channel'])) if c[g].get('log_channel') else None
    embed.add_field(name='Log Channel',value=lc.mention if lc else 'Not set')
    await interaction.response.send_message(embed=embed, view=SecurityConfigView())

class SecurityConfigView(discord.ui.View):
    def __init__(self): super().__init__(timeout=600)
    @discord.ui.button(label='Set Log Channel', style=discord.ButtonStyle.primary)
    async def set_logs(self, i, b): await i.response.send_modal(SecurityLogModal())

class SecurityLogModal(discord.ui.Modal, title='Set Security Log'):
    channel_id = discord.ui.TextInput(label='Channel ID', placeholder='Paste the channel ID', required=True)
    async def on_submit(self, i):
        try:
            ch=i.guild.get_channel(int(self.channel_id.value))
            if ch:
                c=load_json(SECURITY_FILE); g=str(i.guild.id)
                if g not in c: c[g]={}
                c[g]['log_channel']=ch.id; save_json(SECURITY_FILE,c)
                await i.response.send_message(f'Log channel: {ch.mention}', ephemeral=True)
            else: await i.response.send_message('Not found!', ephemeral=True)
        except: await i.response.send_message('Invalid ID!', ephemeral=True)

@bot.tree.command(name='inviteconfig', description='Configure invite tracking')
@app_commands.describe(channel='Channel for logs')
async def inviteconfig(interaction: discord.Interaction, channel: discord.TextChannel):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.administrator: await interaction.response.send_message('No permission!', ephemeral=True); return
    c=load_json(INVITE_FILE); g=str(interaction.guild.id)
    if g not in c: c[g]={'enabled':True,'log_channel':None,'invites':{},'left_users':{}}
    c[g]['enabled']=True; c[g]['log_channel']=channel.id; save_json(INVITE_FILE,c)
    try:
        invs=await interaction.guild.invites()
        for inv in invs: invite_tracking[inv.code]={'inviter':inv.inviter.id if inv.inviter else None,'uses':inv.uses}
    except: pass
    await interaction.response.send_message(embed=discord.Embed(title='Invite System',description=f'Log channel: {channel.mention}',color=discord.Color.green()), ephemeral=True)

@bot.tree.command(name='invites', description='View invite stats')
@app_commands.describe(user='User')
async def invites(interaction: discord.Interaction, user: discord.Member = None):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if user is None: user=interaction.user
    c=load_json(INVITE_FILE); g=str(interaction.guild.id)
    if g not in c or 'invites' not in c[g]: await interaction.response.send_message('Not configured!', ephemeral=True); return
    uid=str(user.id); d=c[g]['invites'].get(uid,{'real':0,'fake':0,'left':0})
    embed=discord.Embed(title=f'Invites for {user.name}',color=discord.Color.orange(),timestamp=datetime.now())
    embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
    embed.add_field(name='Real',value=str(d.get('real',0)),inline=True)
    embed.add_field(name='Fake/Alts',value=str(d.get('fake',0)),inline=True)
    embed.add_field(name='Left',value=str(d.get('left',0)),inline=True)
    embed.add_field(name='Total',value=str(d.get('real',0)+d.get('fake',0)),inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='topinvites', description='Top inviters')
async def topinvites(interaction: discord.Interaction):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    c=load_json(INVITE_FILE); g=str(interaction.guild.id)
    if g not in c or 'invites' not in c[g]: await interaction.response.send_message('Not configured!', ephemeral=True); return
    data=c[g]['invites']
    if not data: await interaction.response.send_message('No data!', ephemeral=True); return
    rankings=[]
    for uid,d in data.items():
        total=d.get('real',0)+d.get('fake',0)
        m=interaction.guild.get_member(int(uid))
        if m and total>0: rankings.append({'name':m.name,'real':d.get('real',0),'fake':d.get('fake',0),'left':d.get('left',0),'total':total})
    rankings.sort(key=lambda x:x['total'],reverse=True)
    top=rankings[:10]
    if not top: await interaction.response.send_message('No data!', ephemeral=True); return
    embed=discord.Embed(title='Top Inviters',color=discord.Color.gold(),timestamp=datetime.now())
    desc=''
    for i,u in enumerate(top): desc+=f'{i+1}. **{u["name"]}** - {u["total"]} invites (Real: {u["real"]} | Fake: {u["fake"]} | Left: {u["left"]})\n'
    embed.description=desc
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='membercount', description='Server member count')
async def membercount(interaction: discord.Interaction):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    g=interaction.guild
    total=g.member_count; humans=len([m for m in g.members if not m.bot]); bots=total-humans; online=len([m for m in g.members if m.status!=discord.Status.offline])
    embed=discord.Embed(title=f'{g.name} Members',color=discord.Color.orange(),timestamp=datetime.now())
    embed.set_thumbnail(url=g.icon.url if g.icon else None)
    embed.add_field(name='Total',value=str(total),inline=True); embed.add_field(name='Humans',value=str(humans),inline=True)
    embed.add_field(name='Bots',value=str(bots),inline=True); embed.add_field(name='Online',value=str(online),inline=True)
    await interaction.response.send_message(embed=embed)
@bot.tree.command(name='ticketconfig', description='Configure tickets')
async def ticketconfig(interaction: discord.Interaction):
    if maintenance_mode and interaction.user.id != BOT_OWNER_ID: await interaction.response.send_message('Bot under maintenance.', ephemeral=True); return
    if interaction.user.id != BOT_OWNER_ID and not interaction.user.guild_permissions.administrator: await interaction.response.send_message('No permission!', ephemeral=True); return
    c=load_json(CONFIG_FILE); g=str(interaction.guild.id)
    if g not in c: c[g]={}; save_json(CONFIG_FILE,c)
    await interaction.response.send_message(embed=discord.Embed(title='Ticket System',description='Choose an option:',color=discord.Color.orange()),view=ChoiceView(),ephemeral=True)

class ChoiceView(discord.ui.View):
    def __init__(self): super().__init__(timeout=600)
    @discord.ui.button(label='Create New Panel', style=discord.ButtonStyle.green)
    async def new(self,i,b):
        cfg={'staff_role_ids':[],'log_channel_id':None,'category_id':None,'panel_channel_id':None,'panel_msg_id':None,'embed_title_open':'Ticket System','embed_desc_open':'Click the button below to open a ticket!','embed_footer_open':'Click the button below','embed_color':'#FFA500','embed_title_ticket':'Ticket Opened','embed_desc_ticket':'Hello {user}, describe your issue.','embed_footer_ticket':'Use the buttons below','btn_color_open':'green','btn_color_close':'red','btn_color_claim':'blue','btn_color_panel':'gray','send_dm':False,'dm_message':'Your ticket has been mentioned!'}
        await i.response.edit_message(embed=create_config_embed(i,cfg),view=ConfigView())
    @discord.ui.button(label='Configure Existing', style=discord.ButtonStyle.blurple)
    async def existing(self,i,b):
        c=load_json(CONFIG_FILE); g=str(i.guild.id)
        if not c.get(g): await i.response.send_message('No panel!',ephemeral=True); return
        await i.response.edit_message(embed=create_config_embed(i,c[g]),view=ConfigView())

def create_config_embed(i,cfg):
    embed=discord.Embed(title='Ticket Configuration',description='Use the buttons below:',color=discord.Color.orange())
    roles=[i.guild.get_role(rid) for rid in cfg.get('staff_role_ids',[]) if i.guild.get_role(rid)]
    logs=i.guild.get_channel(cfg.get('log_channel_id')) if cfg.get('log_channel_id') else None
    cat=i.guild.get_channel(cfg.get('category_id')) if cfg.get('category_id') else None
    pc=i.guild.get_channel(cfg.get('panel_channel_id')) if cfg.get('panel_channel_id') else None
    embed.add_field(name='Staff Roles',value=', '.join([r.mention for r in roles]) if roles else 'Not set',inline=False)
    embed.add_field(name='Log Channel',value=logs.mention if logs else 'Not set',inline=False)
    embed.add_field(name='Category',value=cat.name if cat else 'Not set',inline=False)
    embed.add_field(name='Panel Channel',value=pc.mention if pc else 'Not set',inline=False)
    embed.add_field(name='Color',value=cfg.get('embed_color','#FFA500'),inline=True)
    embed.add_field(name='DM',value='Yes' if cfg.get('send_dm') else 'No',inline=True)
    return embed

class ConfigView(discord.ui.View):
    def __init__(self): super().__init__(timeout=600)
    @discord.ui.button(label='Set Roles',style=discord.ButtonStyle.primary,row=1)
    async def btn_roles(self,i,b): await i.response.send_modal(RoleModal())
    @discord.ui.button(label='Set Logs',style=discord.ButtonStyle.primary,row=1)
    async def btn_logs(self,i,b): await i.response.send_modal(LogModal())
    @discord.ui.button(label='Set Category',style=discord.ButtonStyle.primary,row=1)
    async def btn_cat(self,i,b): await i.response.send_modal(CategoryModal())
    @discord.ui.button(label='Set Color',style=discord.ButtonStyle.primary,row=2)
    async def btn_color(self,i,b): await i.response.send_modal(ColorModal())
    @discord.ui.button(label='Panel Embed',style=discord.ButtonStyle.secondary,row=2)
    async def btn_pe(self,i,b): await i.response.send_modal(PanelEmbedModal())
    @discord.ui.button(label='Ticket Embed',style=discord.ButtonStyle.secondary,row=2)
    async def btn_te(self,i,b): await i.response.send_modal(TicketEmbedModal())
    @discord.ui.button(label='DM Settings',style=discord.ButtonStyle.secondary,row=3)
    async def btn_dm(self,i,b): await i.response.send_modal(DMModal())
    @discord.ui.button(label='Button Colors',style=discord.ButtonStyle.secondary,row=3)
    async def btn_colors(self,i,b): await i.response.send_modal(ButtonColorsModal())
    @discord.ui.button(label='Create Panel',style=discord.ButtonStyle.green,row=4)
    async def btn_create(self,i,b):
        c=load_json(CONFIG_FILE); g=str(i.guild.id)
        if not c[g].get('staff_role_ids'): await i.response.send_message('Set staff roles first!',ephemeral=True); return
        msg=await create_panel(i.channel,c[g])
        c[g]['panel_channel_id']=i.channel.id; c[g]['panel_msg_id']=msg.id; save_json(CONFIG_FILE,c)
        await i.response.send_message('Panel created!',ephemeral=True)
    @discord.ui.button(label='Resend Panel',style=discord.ButtonStyle.blurple,row=4)
    async def btn_resend(self,i,b):
        c=load_json(CONFIG_FILE); g=str(i.guild.id)
        if not c[g].get('staff_role_ids'): await i.response.send_message('Set staff roles first!',ephemeral=True); return
        ch_id=c[g].get('panel_channel_id'); msg_id=c[g].get('panel_msg_id')
        if not ch_id: await i.response.send_message('No panel channel!',ephemeral=True); return
        ch=i.guild.get_channel(int(ch_id))
        if not ch: await i.response.send_message('Channel not found!',ephemeral=True); return
        if msg_id:
            try: old=await ch.fetch_message(int(msg_id)); await old.delete()
            except: pass
        nm=await create_panel(ch,c[g]); c[g]['panel_msg_id']=nm.id; save_json(CONFIG_FILE,c)
        await i.response.send_message(f'Panel updated in {ch.mention}!',ephemeral=True)

class RoleModal(discord.ui.Modal, title='Set Staff Roles'):
    value=discord.ui.TextInput(label='Role IDs (comma separated)',placeholder='Ex: 123, 456',required=True,style=discord.TextStyle.paragraph)
    async def on_submit(self,i):
        try:
            ids=[x.strip() for x in self.value.value.split(',')]; roles=[]
            c=load_json(CONFIG_FILE); g=str(i.guild.id)
            if g not in c: c[g]={}
            for id_str in ids:
                r=i.guild.get_role(int(id_str))
                if r: roles.append(r)
            if roles:
                c[g]['staff_role_ids']=[r.id for r in roles]; save_json(CONFIG_FILE,c)
                await i.response.send_message(f'Roles: {", ".join([r.mention for r in roles])}',ephemeral=True)
            else: await i.response.send_message('No roles found!',ephemeral=True)
        except: await i.response.send_message('Invalid IDs!',ephemeral=True)

class LogModal(discord.ui.Modal, title='Set Ticket Log'):
    value=discord.ui.TextInput(label='Channel ID',placeholder='Paste ID',required=True)
    async def on_submit(self,i):
        try:
            ch=i.guild.get_channel(int(self.value.value))
            if ch:
                c=load_json(CONFIG_FILE); g=str(i.guild.id)
                if g not in c: c[g]={}
                c[g]['log_channel_id']=ch.id; save_json(CONFIG_FILE,c)
                await i.response.send_message(f'Log channel: {ch.mention}',ephemeral=True)
            else: await i.response.send_message('Not found!',ephemeral=True)
        except: await i.response.send_message('Invalid ID!',ephemeral=True)

class CategoryModal(discord.ui.Modal, title='Set Category'):
    value=discord.ui.TextInput(label='Category ID',placeholder='Paste ID',required=True)
    async def on_submit(self,i):
        try:
            cat=i.guild.get_channel(int(self.value.value))
            if cat and isinstance(cat,discord.CategoryChannel):
                c=load_json(CONFIG_FILE); g=str(i.guild.id)
                if g not in c: c[g]={}
                c[g]['category_id']=cat.id; save_json(CONFIG_FILE,c)
                await i.response.send_message(f'Category: {cat.name}',ephemeral=True)
            else: await i.response.send_message('Not found!',ephemeral=True)
        except: await i.response.send_message('Invalid ID!',ephemeral=True)

class ColorModal(discord.ui.Modal, title='Set Color'):
    value=discord.ui.TextInput(label='Hex (6 chars)',placeholder='Ex: #FFA500',required=True)
    async def on_submit(self,i):
        c=self.value.value.replace('#','').strip()
        if len(c)==6:
            try:
                int(c,16); config=load_json(CONFIG_FILE); g=str(i.guild.id)
                if g not in config: config[g]={}
                config[g]['embed_color']=f'#{c}'; save_json(CONFIG_FILE,config)
                await i.response.send_message(embed=discord.Embed(title='Color Set!',description=f'Color: `#{c}`',color=int(c,16)),ephemeral=True)
            except: await i.response.send_message('Invalid!',ephemeral=True)
        else: await i.response.send_message('6 chars!',ephemeral=True)

class PanelEmbedModal(discord.ui.Modal, title='Panel Embed'):
    embed_title=discord.ui.TextInput(label='Title',placeholder='Ticket System',required=True)
    embed_description=discord.ui.TextInput(label='Description',placeholder='Click below to open!',required=True,style=discord.TextStyle.paragraph)
    embed_footer=discord.ui.TextInput(label='Footer',placeholder='Click the button',required=True)
    async def on_submit(self,i):
        c=load_json(CONFIG_FILE); g=str(i.guild.id)
        if g not in c: c[g]={}
        c[g]['embed_title_open']=self.embed_title.value; c[g]['embed_desc_open']=self.embed_description.value; c[g]['embed_footer_open']=self.embed_footer.value
        save_json(CONFIG_FILE,c); await i.response.send_message('Panel embed configured!',ephemeral=True)

class TicketEmbedModal(discord.ui.Modal, title='Ticket Embed'):
    embed_title=discord.ui.TextInput(label='Title',placeholder='Ticket Opened',required=True)
    embed_description=discord.ui.TextInput(label='Description ({user}=mention)',placeholder='Hello {user}, describe your issue.',required=True,style=discord.TextStyle.paragraph)
    embed_footer=discord.ui.TextInput(label='Footer',placeholder='Use the buttons below',required=True)
    async def on_submit(self,i):
        c=load_json(CONFIG_FILE); g=str(i.guild.id)
        if g not in c: c[g]={}
        c[g]['embed_title_ticket']=self.embed_title.value; c[g]['embed_desc_ticket']=self.embed_description.value; c[g]['embed_footer_ticket']=self.embed_footer.value
        save_json(CONFIG_FILE,c); await i.response.send_message('Ticket embed configured!',ephemeral=True)

class DMModal(discord.ui.Modal, title='DM Settings'):
    send=discord.ui.TextInput(label='Send DM? (yes/no)',placeholder='yes',required=True)
    message=discord.ui.TextInput(label='Message',placeholder='DM text',required=False,style=discord.TextStyle.paragraph)
    async def on_submit(self,i):
        c=load_json(CONFIG_FILE); g=str(i.guild.id)
        if g not in c: c[g]={}
        c[g]['send_dm']=self.send.value.lower()=='yes'
        if self.message.value: c[g]['dm_message']=self.message.value
        save_json(CONFIG_FILE,c); await i.response.send_message('DM configured!',ephemeral=True)

class ButtonColorsModal(discord.ui.Modal, title='Button Colors'):
    open_btn=discord.ui.TextInput(label='Open (green/blue/red/gray)',placeholder='green',required=True)
    close_btn=discord.ui.TextInput(label='Close',placeholder='red',required=True)
    claim_btn=discord.ui.TextInput(label='Claim',placeholder='blue',required=True)
    panel_btn=discord.ui.TextInput(label='Panel',placeholder='gray',required=True)
    async def on_submit(self,i):
        c=load_json(CONFIG_FILE); g=str(i.guild.id)
        if g not in c: c[g]={}
        colors={'open':self.open_btn.value,'close':self.close_btn.value,'claim':self.claim_btn.value,'panel':self.panel_btn.value}
        for k,v in colors.items():
            if v.lower() in ['green','blue','red','gray']: c[g][f'btn_color_{k}']=v.lower()
        save_json(CONFIG_FILE,c); await i.response.send_message('Colors configured!',ephemeral=True)

def get_style(color):
    if color=='green': return discord.ButtonStyle.green
    elif color=='blue': return discord.ButtonStyle.blurple
    elif color=='red': return discord.ButtonStyle.red
    return discord.ButtonStyle.gray

class TicketView(discord.ui.View):
    def __init__(self,config): super().__init__(timeout=None); self.config=config
    @discord.ui.button(label='Open Ticket',custom_id='open_ticket_perm')
    async def open(self,interaction: discord.Interaction,button: discord.ui.Button):
        if maintenance_mode: await interaction.response.send_message('Bot under maintenance. Tickets unavailable.',ephemeral=True); return
        button.style=get_style(self.config.get('btn_color_open','green'))
        c=load_json(CONFIG_FILE); g=str(interaction.guild.id)
        for cid,d in open_tickets.items():
            if d['user_id']==interaction.user.id:
                ch=interaction.guild.get_channel(int(cid))
                if ch: await interaction.response.send_message(f'You already have a ticket at {ch.mention}!',ephemeral=True); return
        guild=interaction.guild
        rids=c[g].get('staff_role_ids',[]); roles=[guild.get_role(rid) for rid in rids if guild.get_role(rid)]
        cat_id=c[g].get('category_id'); cat=guild.get_channel(int(cat_id)) if cat_id else interaction.channel.category
        ow={guild.default_role:discord.PermissionOverwrite(read_messages=False),interaction.user:discord.PermissionOverwrite(read_messages=True,send_messages=True),guild.me:discord.PermissionOverwrite(read_messages=True,send_messages=True)}
        for role in roles: ow[role]=discord.PermissionOverwrite(read_messages=True,send_messages=True)
        try: ch=await guild.create_text_channel(name=f'ticket-{interaction.user.name}',category=cat,overwrites=ow)
        except Exception as e: await interaction.response.send_message(f'Error: {e}',ephemeral=True); return
        open_tickets[str(ch.id)]={'user_id':interaction.user.id,'claimed_by':None,'created_at':datetime.now()}
        ci=int(c[g]['embed_color'].replace('#',''),16)
        desc=c[g]['embed_desc_ticket'].replace('{user}',interaction.user.mention)
        embed=discord.Embed(title=c[g]['embed_title_ticket'],description=desc,color=ci)
        embed.set_footer(text=c[g].get('embed_footer_ticket',''))
        rm=' '.join([r.mention for r in roles]) if roles else ''
        view=TicketControlView(c[g])
        await ch.send(content=rm,embed=embed,view=view)
        await interaction.response.send_message(f'Ticket created! {ch.mention}',ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self,config): super().__init__(timeout=None); self.config=config
    def is_staff(self,i):
        if i.user.id==BOT_OWNER_ID: return True
        rids=self.config.get('staff_role_ids',[]); urs=[r.id for r in i.user.roles]
        return any(rid in urs for rid in rids) or i.user.guild_permissions.administrator
    @discord.ui.button(label='Close',custom_id='close_ticket_perm')
    async def close(self,i,b):
        if not self.is_staff(i): await i.response.send_message('Only staff!',ephemeral=True); return
        b.style=get_style(self.config.get('btn_color_close','red'))
        if str(i.channel.id) not in open_tickets: await i.response.send_message('Invalid!',ephemeral=True); return
        await i.response.send_message('Closing in 5 seconds...')
        ch=i.channel
        try: await save_logs(ch,i.user)
        except: pass
        await asyncio.sleep(5); open_tickets.pop(str(i.channel.id),None); await ch.delete()
    @discord.ui.button(label='Claim',custom_id='claim_ticket_perm')
    async def claim(self,i,b):
        if not self.is_staff(i): await i.response.send_message('Only staff!',ephemeral=True); return
        b.style=get_style(self.config.get('btn_color_claim','blue'))
        cid=str(i.channel.id)
        if cid not in open_tickets: await i.response.send_message('Invalid!',ephemeral=True); return
        if open_tickets[cid]['claimed_by']: await i.response.send_message('Already claimed!',ephemeral=True); return
        open_tickets[cid]['claimed_by']=i.user.id
        await i.channel.set_permissions(i.user,read_messages=True,send_messages=True)
        await i.response.send_message(f'Claimed by {i.user.mention}')
    @discord.ui.button(label='Panel',custom_id='panel_ticket_perm')
    async def panel(self,i,b):
        if not self.is_staff(i): await i.response.send_message('Only staff!',ephemeral=True); return
        b.style=get_style(self.config.get('btn_color_panel','gray'))
        if str(i.channel.id) not in open_tickets: await i.response.send_message('Invalid!',ephemeral=True); return
        await i.response.send_message('Choose an option:',view=PanelView(),ephemeral=True)

class PanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=600)
    @discord.ui.button(label='Add Member',style=discord.ButtonStyle.green)
    async def add(self,i,b):
        waiting_mention[str(i.channel.id)]={'author_id':i.user.id,'action':'add'}
        await i.response.send_message('Mention the user to add:',ephemeral=True)
    @discord.ui.button(label='Remove Member',style=discord.ButtonStyle.red)
    async def remove(self,i,b):
        waiting_mention[str(i.channel.id)]={'author_id':i.user.id,'action':'remove'}
        await i.response.send_message('Mention the user to remove:',ephemeral=True)
    @discord.ui.button(label='Mention User',style=discord.ButtonStyle.blurple)
    async def mention(self,i,b):
        cid=str(i.channel.id)
        if cid not in open_tickets: await i.response.send_message('Invalid!',ephemeral=True); return
        c=load_json(CONFIG_FILE); g=str(i.guild.id)
        user=i.guild.get_member(open_tickets[cid]['user_id'])
        if user:
            msg=await i.channel.send(f'{user.mention}'); await asyncio.sleep(3); await msg.delete()
            if c[g].get('send_dm'):
                try: await user.send(f'{c[g].get("dm_message","")}\n{i.channel.mention}')
                except: pass
        await i.response.send_message('User mentioned!',ephemeral=True)

async def create_panel(channel,config):
    c=int(config['embed_color'].replace('#',''),16)
    embed=discord.Embed(title=config['embed_title_open'],description=config['embed_desc_open'],color=c)
    embed.set_footer(text=config.get('embed_footer_open',''))
    return await channel.send(embed=embed,view=TicketView(config))

if __name__=='__main__':
    bot.run(os.getenv('TOKEN'))