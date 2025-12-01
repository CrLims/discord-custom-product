import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from dotenv import load_dotenv
from datetime import datetime

# ============================================
# LOAD ENV
# ============================================
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0"))
ALLOWED_USER_IDS = [int(uid) for uid in os.getenv("ALLOWED_USER_IDS", "").split(",") if uid.strip()]
TESTIMONI_CHANNEL_ID = int(os.getenv("TESTIMONI_CHANNEL_ID", "0"))

# Emoji
SOLD_EMOJI = "<:sold:1442214201274794097>"

# ============================================
# DISCORD INTENTS & BOT
# ============================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ============================================
# FILE PATHS
# ============================================
PRODUCTS_FILE = "products.json"       # { "Product Name": { "stock": int, "price": int } }
MAIN_MESSAGE_FILE = "main_message.json"
TRANSACTIONS_FILE = "transactions.json"


# ============================================
# HELPER FORMAT
# ============================================
def rupiah(n: int) -> str:
    """Format angka ke Rp style: 5000 -> '5.000'."""
    return f"{n:,}".replace(",", ".")


# ============================================
# JSON HELPERS
# ============================================
def load_products() -> dict:
    """
    Struktur:
    {
        "Nama Produk": {
            "stock": int,
            "price": int
        },
        ...
    }
    """
    try:
        with open(PRODUCTS_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def save_products(data: dict):
    with open(PRODUCTS_FILE, "w") as f:
        json.dump(data, f, indent=4)


def load_transactions() -> dict:
    try:
        with open(TRANSACTIONS_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def save_transactions(data: dict):
    with open(TRANSACTIONS_FILE, "w") as f:
        json.dump(data, f, indent=4)


def load_main_message():
    try:
        with open(MAIN_MESSAGE_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return None
    except FileNotFoundError:
        return None
    except Exception:
        return None


def save_main_message(channel_id: int, message_id: int):
    with open(MAIN_MESSAGE_FILE, "w") as f:
        json.dump({"channel_id": channel_id, "message_id": message_id}, f, indent=4)


# ============================================
# EMBED UTAMA MULTI-PRODUK
# ============================================
def build_main_embed() -> discord.Embed:
    products = load_products()

    embed = discord.Embed(
        title="<a:ToaJoget:1442231853007507567> STORE ITEM FISH IT BY KAEPBLOX <a:ToaJoget:1442231853007507567>",
        color=discord.Color.from_rgb(15, 15, 25)
    )

    if not products:
        embed.description = (
            "Belum ada produk terdaftar.\n"
            "Admin bisa menambahkan produk dengan command `/addproduct`."
        )
        embed.set_footer(text="KaepBlox • Ikan Secret Tumbal")
        return embed

    lines = []
    for name, pdata in products.items():
        stock = int(pdata.get("stock", 0))
        price = int(pdata.get("price", 0))

        stock_display = SOLD_EMOJI if stock <= 0 else str(stock)
        price_display = rupiah(price)

        lines.append(f"**{name}**")
        lines.append(f"<a:PANAHBIRU:1437484514921283676>  Stock : {stock_display}")
        lines.append(f"<a:PANAHBIRU:1437484514921283676>  Price : Rp{price_display} <:duit:1433825063333003275>")
        lines.append("")

    embed.description = "\n".join(lines).strip()
    embed.set_footer(text="KaepBlox • Ikan Secret Tumbal")

    return embed


async def refresh_main_embed(client: discord.Client):
    """Refresh embed utama (stock/harga) & view select, tanpa kirim message baru."""
    try:
        state = load_main_message()
        if not state:
            return

        channel = client.get_channel(state.get("channel_id"))
        if not channel:
            return

        try:
            msg = await channel.fetch_message(state.get("message_id"))
        except Exception:
            return

        embed = build_main_embed()
        view = ProductSelectView()
        await msg.edit(embed=embed, view=view)
    except Exception as e:
        print(f"[refresh_main_embed] Error: {e}")


# ============================================
# MODAL PEMBELIAN PER PRODUK
# ============================================
class PurchaseModal(discord.ui.Modal, title="Pembelian SC Tumbal"):
    amount = discord.ui.TextInput(
        label="Mau beli berapa SC?",
        placeholder="Contoh: 5",
        required=True,
        max_length=10
    )

    def __init__(self, product_name: str):
        super().__init__()
        self.product_name = product_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value)
        except ValueError:
            return await interaction.response.send_message(
                "❌ Masukkan angka yang valid!",
                ephemeral=True
            )

        if amount <= 0:
            return await interaction.response.send_message(
                "❌ Jumlah harus lebih dari 0!",
                ephemeral=True
            )

        # Cek produk
        products = load_products()
        product = products.get(self.product_name)
        if not product:
            return await interaction.response.send_message(
                "❌ Produk tidak ditemukan (mungkin sudah dihapus admin).",
                ephemeral=True
            )

        unit_price = int(product.get("price", 0))
        stock_now = int(product.get("stock", 0))

        # Cek pending transaksi produk ini
        transactions = load_transactions()
        pending_stock = sum(
            t["amount"]
            for t in transactions.values()
            if t.get("status") == "pending" and t.get("product") == self.product_name
        )
        available_stock = stock_now - pending_stock

        if amount > available_stock:
            return await interaction.response.send_message(
                f"❌ **Stock {self.product_name} tidak mencukupi!**\n"
                f"Stock tersedia: **{available_stock}**\n"
                f"Stock dalam transaksi: **{pending_stock}**\n"
                f"Kamu minta: **{amount}**",
                ephemeral=True
            )

        # Buat / cari kategori ticket
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message(
                "❌ Guild tidak ditemukan.",
                ephemeral=True
            )

        category = None
        if TICKET_CATEGORY_ID:
            ch = guild.get_channel(TICKET_CATEGORY_ID)
            if isinstance(ch, discord.CategoryChannel):
                category = ch

        if category is None:
            category = discord.utils.get(guild.categories, name="TICKETS")
            if category is None:
                category = await guild.create_category("TICKETS")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        safe_name = self.product_name.replace(" ", "-").lower()
        ticket_channel = await category.create_text_channel(
            name=f"ticket-{safe_name}-{interaction.user.name}",
            overwrites=overwrites
        )

        total_price = amount * unit_price

        # Simpan transaksi
        transactions = load_transactions()
        transactions[str(ticket_channel.id)] = {
            "user_id": interaction.user.id,
            "product": self.product_name,
            "amount": amount,
            "unit_price": unit_price,
            "total_price": total_price,
            "status": "pending",
            "created_at": datetime.now().isoformat()
        }
        save_transactions(transactions)

        # Buat embed ticket
        embed = discord.Embed(
            title="🎫 Ticket Pembelian SC Tumbal",
            description=(
                f"👤 Pembeli: {interaction.user.mention}\n"
                f"🧾 Produk: **{self.product_name}**\n\n"
                "Silakan tunggu admin untuk memproses pesanan kamu.\n\n"
                "📌 **Reminder:**\n"
                "• Jangan spam chat.\n"
                "• Proses manual oleh admin.\n"
                "• Tag <@1005129829370318999> / <@1190606903911403650> jika ingin beli.\n"
            ),
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        embed.add_field(
            name="📦 Jumlah Ikan Tumbal",
            value=f"**{amount}** Ikan",
            inline=True
        )
        embed.add_field(
            name="💰 Total Harga",
            value=f"**Rp{rupiah(total_price)}** <:duit:1433825063333003275>",
            inline=True
        )
        embed.add_field(
            name="Status",
            value="⏳ **Menunggu konfirmasi admin**",
            inline=False
        )
        embed.set_footer(text="KaepBlox — Ticket otomatis ditutup setelah transaksi selesai / dibatalkan")

        view = TicketView(ticket_channel.id)
        await ticket_channel.send(content=interaction.user.mention, embed=embed, view=view)

        await interaction.response.send_message(
            f"✅ Ticket untuk **{self.product_name}** berhasil dibuat! Silakan menuju ke {ticket_channel.mention}",
            ephemeral=True
        )


# ============================================
# VIEW EPHEMERAL: BELI SEKARANG (SETELAH PILIH PRODUK)
# ============================================
class EphemeralBuyView(discord.ui.View):
    def __init__(self, product_name: str):
        super().__init__(timeout=120)
        self.product_name = product_name

    @discord.ui.button(
        label="Beli Sekarang",
        style=discord.ButtonStyle.green,
        emoji="🛒"
    )
    async def beli_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Cek produk & stock
        products = load_products()
        product = products.get(self.product_name)
        if not product:
            return await interaction.response.send_message(
                "❌ Produk tidak ditemukan (mungkin sudah dihapus admin).",
                ephemeral=True
            )

        stock_now = int(product.get("stock", 0))
        if stock_now <= 0:
            return await interaction.response.send_message(
                f"{SOLD_EMOJI} Maaf, stock **{self.product_name}** sedang habis. Tunggu restock ya!",
                ephemeral=True
            )

        modal = PurchaseModal(self.product_name)
        await interaction.response.send_modal(modal)


# ============================================
# SELECT MENU PRODUK (DI EMBED UTAMA)
# ============================================
class ProductSelect(discord.ui.Select):
    def __init__(self):
        products = load_products()

        options = []
        for name, pdata in products.items():
            stock = int(pdata.get("stock", 0))
            price = int(pdata.get("price", 0))
            options.append(
                discord.SelectOption(
                    label=name[:100],
                    value=name,
                    description=f"Stock: {stock} • Rp{rupiah(price)}"
                )
            )

        if not options:
            options = [
                discord.SelectOption(
                    label="Belum ada produk",
                    value="__none",
                    description="Minta admin tambahkan produk dulu."
                )
            ]

        super().__init__(
            placeholder="🔽 Pilih produk yang ingin dibeli",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="product_select_menu"
        )

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]

        if value == "__none":
            await interaction.response.send_message(
                "❌ Belum ada produk yang bisa dibeli. Minta admin menambahkan produk dulu.",
                ephemeral=True
            )
            return

        products = load_products()
        product = products.get(value)
        if not product:
            await interaction.response.send_message(
                "❌ Produk tidak ditemukan!",
                ephemeral=True
            )
            return

        stock_now = int(product.get("stock", 0))
        if stock_now <= 0:
            await interaction.response.send_message(
                f"{SOLD_EMOJI} Stock **{value}** habis. Tunggu restock ya!",
                ephemeral=True
            )
            return

        # Kirim ephemeral "Beli Sekarang"
        view = EphemeralBuyView(value)
        await interaction.response.send_message(
            f"📌 Kamu memilih produk: **{value}**\n"
            f"Klik tombol di bawah untuk melanjutkan pembelian.",
            view=view,
            ephemeral=True
        )

        # RESET SELECT SUPAYA BISA KLIK PRODUK YANG SAMA BERKALI-KALI
        try:
            await interaction.message.edit(view=ProductSelectView())
        except Exception as e:
            print(f"Error reset select view: {e}")


class ProductSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ProductSelect())


# ============================================
# VIEW TICKET (ADMIN: SUCCESS / CANCEL)
# ============================================
class TicketView(discord.ui.View):
    def __init__(self, channel_id: int):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    @discord.ui.button(label="Success", style=discord.ButtonStyle.success, emoji="✅")
    async def success_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ALLOWED_USER_IDS:
            return await interaction.response.send_message(
                "❌ Kamu tidak memiliki izin untuk menggunakan tombol ini!",
                ephemeral=True
            )

        transactions = load_transactions()
        tx = transactions.get(str(self.channel_id))
        if not tx:
            return await interaction.response.send_message(
                "❌ Data transaksi tidak ditemukan!",
                ephemeral=True
            )

        if tx.get("status") != "pending":
            return await interaction.response.send_message(
                "❌ Transaksi ini sudah diproses sebelumnya!",
                ephemeral=True
            )

        product_name = tx.get("product")
        amount = tx.get("amount", 0)
        total_price = tx.get("total_price", 0)

        # Kurangi stock produk
        products = load_products()
        if product_name in products:
            products[product_name]["stock"] = max(0, int(products[product_name].get("stock", 0)) - amount)
            save_products(products)

        # Update transaksi
        tx["status"] = "success"
        tx["processed_by"] = interaction.user.id
        tx["processed_at"] = datetime.now().isoformat()
        transactions[str(self.channel_id)] = tx
        save_transactions(transactions)

        # Update embed di ticket (HANYA message bot sendiri)
        channel = interaction.channel
        if isinstance(channel, discord.TextChannel):
            async for msg in channel.history(limit=10):
                if msg.author.id != interaction.client.user.id:
                    continue
                if not msg.embeds:
                    continue

                embed = msg.embeds[0]
                embed.color = discord.Color.green()
                if len(embed.fields) >= 3:
                    embed.set_field_at(2, name="Status", value="✅ **Transaksi Berhasil**", inline=False)
                else:
                    embed.add_field(name="Status", value="✅ **Transaksi Berhasil**", inline=False)
                embed.add_field(name="Diproses oleh", value=interaction.user.mention, inline=False)
                await msg.edit(embed=embed, view=None)
                break

        # Log testimoni
        try:
            if TESTIMONI_CHANNEL_ID:
                log_ch = interaction.client.get_channel(TESTIMONI_CHANNEL_ID)
                if isinstance(log_ch, discord.TextChannel):
                    buyer = None
                    if isinstance(channel, discord.TextChannel):
                        buyer = channel.guild.get_member(tx["user_id"])

                    log_embed = discord.Embed(
                        title="✅ Testimoni Pembelian Ikan Tumbal",
                        color=discord.Color.green(),
                        timestamp=datetime.now()
                    )
                    log_embed.add_field(
                        name="👤 Pembeli",
                        value=buyer.mention if buyer else f"`{tx['user_id']}`",
                        inline=True
                    )
                    log_embed.add_field(name="🧾 Produk", value=product_name or "-", inline=True)
                    log_embed.add_field(name="📦 Jumlah", value=f"**{amount}** Ikan", inline=True)
                    log_embed.add_field(
                        name="💰 Total",
                        value=f"**Rp{rupiah(total_price)}**",
                        inline=False
                    )
                    log_embed.add_field(
                        name="🛠 Diproses oleh",
                        value=interaction.user.mention,
                        inline=True
                    )
                    log_embed.set_footer(text="KaepBlox • Log sukses otomatis")
                    await log_ch.send(embed=log_embed)
        except Exception as e:
            print(f"[TicketView.success_button] Error send testimoni: {e}")

        # Refresh main embed (update stock)
        await refresh_main_embed(interaction.client)

        await interaction.response.send_message(
            f"✅ Transaksi **{product_name}** berhasil! Stock tersisa: **{products.get(product_name, {}).get('stock', 0)}**",
            ephemeral=False
        )

        # Tutup ticket setelah 10 detik
        await interaction.followup.send("Ticket akan ditutup dalam 10 detik...")
        import asyncio
        await asyncio.sleep(10)
        await channel.delete()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ALLOWED_USER_IDS:
            return await interaction.response.send_message(
                "❌ Kamu tidak memiliki izin untuk menggunakan tombol ini!",
                ephemeral=True
            )

        transactions = load_transactions()
        tx = transactions.get(str(self.channel_id))
        if not tx:
            return await interaction.response.send_message(
                "❌ Data transaksi tidak ditemukan!",
                ephemeral=True
            )

        if tx.get("status") != "pending":
            return await interaction.response.send_message(
                "❌ Transaksi ini sudah diproses sebelumnya!",
                ephemeral=True
            )

        tx["status"] = "cancelled"
        tx["processed_by"] = interaction.user.id
        tx["processed_at"] = datetime.now().isoformat()
        transactions[str(self.channel_id)] = tx
        save_transactions(transactions)

        # Update embed di ticket (HANYA message bot sendiri)
        channel = interaction.channel
        if isinstance(channel, discord.TextChannel):
            async for msg in channel.history(limit=10):
                if msg.author.id != interaction.client.user.id:
                    continue
                if not msg.embeds:
                    continue

                embed = msg.embeds[0]
                embed.color = discord.Color.red()
                if len(embed.fields) >= 3:
                    embed.set_field_at(2, name="Status", value="❌ **Transaksi Dibatalkan**", inline=False)
                else:
                    embed.add_field(name="Status", value="❌ **Transaksi Dibatalkan**", inline=False)
                embed.add_field(name="Dibatalkan oleh", value=interaction.user.mention, inline=False)
                await msg.edit(embed=embed, view=None)
                break

        await interaction.response.send_message(
            "❌ Transaksi dibatalkan!",
            ephemeral=False
        )

        await interaction.followup.send("Ticket akan ditutup dalam 10 detik...")
        import asyncio
        await asyncio.sleep(10)
        await channel.delete()


# ============================================
# EVENTS
# ============================================
@bot.event
async def on_ready():
    print(f"{bot.user} telah online!")

    # Persistent view untuk select produk
    bot.add_view(ProductSelectView())

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")

    # Setup / update embed utama
    channel = bot.get_channel(CHANNEL_ID)
    if not isinstance(channel, discord.TextChannel):
        print("Channel utama tidak ditemukan atau bukan TextChannel.")
        return

    embed = build_main_embed()

    state = load_main_message()
    msg = None

    if state and state.get("channel_id") == CHANNEL_ID:
        try:
            msg = await channel.fetch_message(state.get("message_id"))
        except Exception:
            msg = None

    view = ProductSelectView()

    if msg:
        await msg.edit(embed=embed, view=view)
        print(f"Embed utama diupdate (reuse message {msg.id}) di channel {CHANNEL_ID}")
    else:
        sent = await channel.send(embed=embed, view=view)
        save_main_message(CHANNEL_ID, sent.id)
        print(f"Embed baru dikirim ke channel {CHANNEL_ID}, message_id {sent.id} disimpan.")


# ============================================
# SLASH COMMANDS (ADMIN)
# ============================================

@bot.tree.command(name="addproduct", description="Tambah/Update produk (Admin only)")
@app_commands.describe(
    name="Nama produk",
    stock="Stock awal",
    price="Harga per SC (dalam Rupiah)"
)
async def addproduct(interaction: discord.Interaction, name: str, stock: int, price: int):
    if interaction.user.id not in ALLOWED_USER_IDS:
        return await interaction.response.send_message(
            "❌ Kamu tidak memiliki izin untuk menggunakan command ini!",
            ephemeral=True
        )

    name = name.strip()
    if not name:
        return await interaction.response.send_message(
            "❌ Nama produk tidak boleh kosong.",
            ephemeral=True
        )

    if stock < 0 or price <= 0:
        return await interaction.response.send_message(
            "❌ Stock tidak boleh negatif dan harga harus lebih dari 0!",
            ephemeral=True
        )

    products = load_products()
    is_new = name not in products

    products[name] = {
        "stock": stock,
        "price": price
    }
    save_products(products)

    await interaction.response.send_message(
        f"✅ Produk **{name}** {'ditambahkan' if is_new else 'diupdate'}.\n"
        f"Stock: **{stock}**\n"
        f"Harga: **Rp{rupiah(price)}**",
        ephemeral=True
    )

    await refresh_main_embed(interaction.client)


@bot.tree.command(name="setstock", description="Atur stock produk (Admin only)")
@app_commands.describe(
    name="Nama produk",
    amount="Stock baru"
)
async def setstock(interaction: discord.Interaction, name: str, amount: int):
    if interaction.user.id not in ALLOWED_USER_IDS:
        return await interaction.response.send_message(
            "❌ Kamu tidak memiliki izin untuk menggunakan command ini!",
            ephemeral=True
        )

    products = load_products()
    if name not in products:
        return await interaction.response.send_message(
            f"❌ Produk **{name}** tidak ditemukan. Tambah dulu pakai `/addproduct`.",
            ephemeral=True
        )

    products[name]["stock"] = max(0, amount)
    save_products(products)

    await interaction.response.send_message(
        f"✅ Stock produk **{name}** diatur menjadi **{products[name]['stock']}**",
        ephemeral=True
    )

    await refresh_main_embed(interaction.client)


@setstock.autocomplete("name")
async def setstock_name_autocomplete(
    interaction: discord.Interaction,
    current: str
):
    products = load_products()
    current_lower = current.lower()
    choices = []
    for pname in products.keys():
        if not current or current_lower in pname.lower():
            choices.append(app_commands.Choice(name=pname, value=pname))
    return choices[:25]


@bot.tree.command(name="setharga", description="Atur harga produk (Admin only)")
@app_commands.describe(
    name="Nama produk",
    price="Harga baru per 1 SC (dalam Rupiah)"
)
async def setharga(interaction: discord.Interaction, name: str, price: int):
    if interaction.user.id not in ALLOWED_USER_IDS:
        return await interaction.response.send_message(
            "❌ Kamu tidak memiliki izin untuk menggunakan command ini!",
            ephemeral=True
        )

    if price <= 0:
        return await interaction.response.send_message(
            "❌ Harga harus lebih dari 0!",
            ephemeral=True
        )

    products = load_products()
    if name not in products:
        return await interaction.response.send_message(
            f"❌ Produk **{name}** tidak ditemukan. Tambah dulu pakai `/addproduct`.",
            ephemeral=True
        )

    products[name]["price"] = price
    save_products(products)

    await interaction.response.send_message(
        f"✅ Harga produk **{name}** diatur menjadi **Rp{rupiah(price)}**",
        ephemeral=True
    )

    await refresh_main_embed(interaction.client)


@setharga.autocomplete("name")
async def setharga_name_autocomplete(
    interaction: discord.Interaction,
    current: str
):
    products = load_products()
    current_lower = current.lower()
    choices = []
    for pname in products.keys():
        if not current or current_lower in pname.lower():
            choices.append(app_commands.Choice(name=pname, value=pname))
    return choices[:25]


@bot.tree.command(name="hapusproduk", description="Hapus produk (Admin only)")
@app_commands.describe(
    name="Nama produk yang akan dihapus"
)
async def hapusproduk(interaction: discord.Interaction, name: str):
    if interaction.user.id not in ALLOWED_USER_IDS:
        return await interaction.response.send_message(
            "❌ Kamu tidak memiliki izin untuk menggunakan command ini!",
            ephemeral=True
        )

    products = load_products()
    if name not in products:
        return await interaction.response.send_message(
            f"❌ Produk **{name}** tidak ditemukan.",
            ephemeral=True
        )

    del products[name]
    save_products(products)

    await interaction.response.send_message(
        f"🗑️ Produk **{name}** berhasil dihapus.",
        ephemeral=True
    )

    await refresh_main_embed(interaction.client)


@hapusproduk.autocomplete("name")
async def hapusproduk_name_autocomplete(
    interaction: discord.Interaction,
    current: str
):
    products = load_products()
    current_lower = current.lower()
    choices = []
    for pname in products.keys():
        if not current or current_lower in pname.lower():
            choices.append(app_commands.Choice(name=pname, value=pname))
    return choices[:25]


@bot.tree.command(name="stock", description="Lihat stock semua produk")
async def stock_cmd(interaction: discord.Interaction):
    products = load_products()
    transactions = load_transactions()

    embed = discord.Embed(
        title="📦 Informasi Stock Produk",
        color=discord.Color.from_rgb(88, 101, 242)
    )

    if not products:
        embed.description = "Belum ada produk terdaftar."
    else:
        for name, pdata in products.items():
            total = int(pdata.get("stock", 0))
            price = int(pdata.get("price", 0))
            pending = sum(
                t["amount"]
                for t in transactions.values()
                if t.get("status") == "pending" and t.get("product") == name
            )
            available = total - pending

            embed.add_field(
                name=f"📦 {name}",
                value=(
                    f"Total: **{total}**\n"
                    f"Pending: **{pending}**\n"
                    f"Tersedia: **{available}**\n"
                    f"Harga: **Rp{rupiah(price)}** <:duit:1433825063333003275>"
                ),
                inline=False
            )

    await interaction.response.send_message(embed=embed, ephemeral=True)


# ============================================
# RUN BOT
# ============================================
if not TOKEN:
    print("DISCORD_TOKEN belum di-set di .env")
else:
    bot.run(TOKEN)
