using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

namespace RoadCraftOfflineMods
{
    public static class Settings
    {
        public const int Limit = 16 * 1024 * 1024;
        static readonly byte[] Key = { 0x9d, 0x64, 0xaa, 0xec };
        static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);
        static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = Limit };

        public static byte[] Transform(byte[] data)
        {
            byte[] result = new byte[data.Length];
            int index = 0, count = 0, marker = 0;
            for (int n = 0; n < data.Length; n++)
            {
                byte value = data[n];
                if (count == marker) { count = 0; marker = value; result[n] = value; }
                else { result[n] = (byte)(value ^ Key[index]); index = (index + 1) & 3; count++; }
            }
            return result;
        }

        public static string Hash(byte[] data)
        {
            using (var md5 = MD5.Create()) return BitConverter.ToString(md5.ComputeHash(data)).Replace("-", "").ToLowerInvariant();
        }

        static uint Adler(byte[] data)
        {
            uint a = 1, b = 0;
            foreach (byte v in data) { a = (a + v) % 65521; b = (b + a) % 65521; }
            return (b << 16) | a;
        }

        public static byte[] Decode(byte[] file)
        {
            if (file.Length < 53 || Encoding.ASCII.GetString(file, 0, 4) != "SSF1") throw new InvalidDataException("This is not an SSF1 settings file.");
            ulong packed = BitConverter.ToUInt64(file, 4), size = BitConverter.ToUInt64(file, 12);
            if (size > Limit || packed != (ulong)(file.Length - 53)) throw new InvalidDataException("The settings file has an invalid length.");
            byte[] payload = file.Skip(53).ToArray();
            if (Encoding.ASCII.GetString(file, 20, 32) != Hash(payload)) throw new InvalidDataException("The settings checksum does not match. No changes made.");
            byte codec = file[52];
            if (codec > 2) throw new InvalidDataException("This settings codec is not supported. No changes made.");
            if (codec == 0)
            {
                if ((ulong)payload.Length != size) throw new InvalidDataException("The settings size does not match.");
                return payload;
            }
            byte[] z = codec == 2 ? Transform(payload) : payload;
            if (z.Length < 6 || (z[0] & 15) != 8 || (z[0] >> 4) > 7 || ((z[0] << 8) + z[1]) % 31 != 0 || (z[1] & 32) != 0)
                throw new InvalidDataException("The settings compression format is not supported.");
            byte[] raw;
            using (var input = new MemoryStream(z, 2, z.Length - 6))
            using (var inflate = new DeflateStream(input, CompressionMode.Decompress))
            using (var output = new MemoryStream())
            {
                byte[] buffer = new byte[4096]; int n;
                while ((n = inflate.Read(buffer, 0, buffer.Length)) > 0)
                {
                    if (output.Length + n > (long)size) throw new InvalidDataException("The expanded settings size does not match.");
                    output.Write(buffer, 0, n);
                }
                raw = output.ToArray();
            }
            int end = z.Length - 4;
            uint checksum = ((uint)z[end] << 24) | ((uint)z[end + 1] << 16) | ((uint)z[end + 2] << 8) | z[end + 3];
            if ((ulong)raw.Length != size || Adler(raw) != checksum) throw new InvalidDataException("The expanded settings checksum does not match.");
            return raw;
        }

        public static byte[] Encode(byte[] raw, byte codec)
        {
            if (raw.Length > Limit || codec > 2) throw new InvalidDataException("Unsupported settings format.");
            byte[] payload = raw;
            if (codec != 0)
            {
                using (var output = new MemoryStream())
                {
                    output.WriteByte(0x78); output.WriteByte(0x9c);
                    using (var deflate = new DeflateStream(output, CompressionLevel.Optimal, true)) deflate.Write(raw, 0, raw.Length);
                    uint checksum = Adler(raw);
                    for (int shift = 24; shift >= 0; shift -= 8) output.WriteByte((byte)(checksum >> shift));
                    payload = output.ToArray();
                }
                if (codec == 2) payload = Transform(payload);
            }
            using (var output = new MemoryStream())
            using (var writer = new BinaryWriter(output))
            {
                writer.Write(Encoding.ASCII.GetBytes("SSF1")); writer.Write((ulong)payload.Length); writer.Write((ulong)raw.Length);
                writer.Write(Encoding.ASCII.GetBytes(Hash(payload))); writer.Write(codec); writer.Write(payload);
                return output.ToArray();
            }
        }

        public static string Text(byte[] file) { return Utf8.GetString(Decode(file)); }

        public static List<string> Mods(string text)
        {
            var root = Json.DeserializeObject(text) as Dictionary<string, object>;
            object userObject;
            if (root == null || !root.TryGetValue("UserSettings", out userObject)) throw new InvalidDataException("This is not user_settings.cfg.");
            var user = userObject as Dictionary<string, object>;
            if (user == null) throw new InvalidDataException("UserSettings is not an object.");
            object value;
            if (!user.TryGetValue("enabledMods", out value)) return new List<string>();
            var array = value as object[];
            if (array == null || array.Any(x => !(x is string))) throw new InvalidDataException("The enabled mod list has an unexpected format.");
            return array.Cast<string>().ToList();
        }

        // Find JSON value spans so other settings retain their exact original text.
        static void White(string s, ref int p) { while (p < s.Length && char.IsWhiteSpace(s[p])) p++; }
        static void Skip(string s, ref int p)
        {
            White(s, ref p);
            if (s[p] == '"')
            {
                p++;
                while (p < s.Length) { char c = s[p++]; if (c == '\\') p++; else if (c == '"') return; }
                throw new InvalidDataException("Unfinished JSON string.");
            }
            if (s[p] == '{' || s[p] == '[')
            {
                char end = s[p++] == '{' ? '}' : ']';
                while (true) { White(s, ref p); if (s[p] == end) { p++; return; } if (s[p] == ',' || s[p] == ':') p++; else Skip(s, ref p); }
            }
            else { while (p < s.Length && ",]}".IndexOf(s[p]) < 0 && !char.IsWhiteSpace(s[p])) p++; }
        }
        static int[] Property(string s, int start, string key)
        {
            int p = start; White(s, ref p);
            if (s[p++] != '{') throw new InvalidDataException("Expected a JSON object.");
            int[] found = null;
            while (true)
            {
                White(s, ref p); if (s[p] == '}') return found ?? new int[] { -1, p };
                int keyStart = p; Skip(s, ref p); string name = Json.Deserialize<string>(s.Substring(keyStart, p - keyStart));
                White(s, ref p); if (s[p++] != ':') throw new InvalidDataException("Invalid JSON property.");
                White(s, ref p); int valueStart = p; Skip(s, ref p);
                if (name == key) { if (found != null) throw new InvalidDataException("Duplicate " + key + " property."); found = new int[] { valueStart, p }; }
                White(s, ref p); if (s[p] == ',') p++; else if (s[p] != '}') throw new InvalidDataException("Invalid JSON object.");
            }
        }

        public static string Change(string text, string id, bool enabled)
        {
            if (!id.StartsWith("local:", StringComparison.Ordinal) || id.Length <= 6 || id.IndexOfAny(new char[] { '/', '\\', '\0' }) >= 0) throw new ArgumentException("Invalid local mod name.");
            List<string> mods = Mods(text);
            if (enabled) { if (mods.Contains(id)) return text; mods.Add(id); }
            else { if (!mods.Contains(id)) return text; mods.RemoveAll(x => x == id); }
            int[] user = Property(text, 0, "UserSettings"), span = Property(text, user[0], "enabledMods");
            string array = Json.Serialize(mods), changed;
            if (span[0] >= 0) changed = text.Substring(0, span[0]) + array + text.Substring(span[1]);
            else
            {
                string existing = text.Substring(user[0] + 1, span[1] - user[0] - 1).Trim();
                changed = text.Substring(0, span[1]) + (existing.Length == 0 ? "" : ",") + "\"enabledMods\":" + array + text.Substring(span[1]);
            }
            if (!Mods(changed).SequenceEqual(mods)) throw new InvalidDataException("The new mod list failed verification.");
            return changed;
        }

        public static void RequireClosed()
        {
            int current = Process.GetCurrentProcess().Id;
            foreach (var p in Process.GetProcesses())
            {
                using (p) if (p.Id != current && p.ProcessName.StartsWith("Roadcraft", StringComparison.OrdinalIgnoreCase) && !p.ProcessName.Equals("RoadCraftOfflineMods", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("Close RoadCraft and its editor before changing mods.");
            }
        }

        public static string Write(string path, byte[] expected, byte[] replacement, bool processCheck)
        {
            Mods(Text(expected)); Mods(Text(replacement));
            if (expected.SequenceEqual(replacement)) return null;
            if (processCheck) RequireClosed();
            if (!File.ReadAllBytes(path).SequenceEqual(expected)) throw new IOException("The settings changed while the tool was open. Refresh and try again.");
            string token = DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N").Substring(0, 8);
            string temporary = path + ".offline-mods-" + token + ".tmp", backup = path + ".offline-mods-" + token + ".bak";
            try
            {
                using (var file = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None)) { file.Write(replacement, 0, replacement.Length); file.Flush(true); }
                if (!File.ReadAllBytes(temporary).SequenceEqual(replacement)) throw new IOException("The temporary settings file failed verification.");
                if (processCheck) RequireClosed();
                if (!File.ReadAllBytes(path).SequenceEqual(expected)) throw new IOException("The settings changed. Refresh and try again.");
                File.Replace(temporary, path, backup, true);
                if (!File.ReadAllBytes(path).SequenceEqual(replacement) || !File.ReadAllBytes(backup).SequenceEqual(expected)) throw new IOException("The saved file or backup failed verification. Backup: " + backup);
                return backup;
            }
            finally { if (File.Exists(temporary)) File.Delete(temporary); }
        }

        public static string Update(string path, string id, bool enabled, bool processCheck)
        {
            byte[] original = File.ReadAllBytes(path); string old = Text(original), changed = Change(old, id, enabled);
            if (old == changed) return null;
            byte[] replacement = Encode(Utf8.GetBytes(changed), original[52]);
            if (Text(replacement) != changed) throw new InvalidDataException("The new settings failed verification.");
            return Write(path, original, replacement, processCheck);
        }
    }

    class ModForm : Form
    {
        TextBox game = new TextBox(); ComboBox profiles = new ComboBox(), mods = new ComboBox();
        Label status = new Label(); string storage; bool preview;
        protected override bool ShowWithoutActivation { get { return preview; } }
        public ModForm()
        {
            Text = "RoadCraft Offline Mods"; Width = 650; Height = 330; MinimumSize = MaximumSize = Size;
            StartPosition = FormStartPosition.CenterScreen; FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false;
            Font = new System.Drawing.Font("Segoe UI", 10);
            LabelAt("Close RoadCraft. Put your .pak in the game's root\\mods folder, then enable it here.", 18, 15, 600);
            LabelAt("Game folder", 18, 56, 100); game.SetBounds(125, 52, 395, 28); Controls.Add(game);
            ButtonAt("Browse", 528, 51, 88, delegate { using (var d = new FolderBrowserDialog()) { d.Description = "Select the RoadCraft folder containing root"; if (d.ShowDialog() == DialogResult.OK) { game.Text = d.SelectedPath; RefreshLists(); } } });
            LabelAt("Profile", 18, 97, 100); profiles.SetBounds(125, 92, 491, 28); profiles.DropDownStyle = ComboBoxStyle.DropDownList; Controls.Add(profiles);
            LabelAt("Mod", 18, 138, 100); mods.SetBounds(125, 133, 491, 28); mods.DropDownStyle = ComboBoxStyle.DropDownList; Controls.Add(mods);
            ButtonAt("Enable", 125, 178, 104, delegate { Toggle(true); }); ButtonAt("Disable", 237, 178, 104, delegate { Toggle(false); });
            ButtonAt("Refresh", 349, 178, 104, delegate { RefreshLists(); }); ButtonAt("Restore backup", 461, 178, 155, Restore);
            status.SetBounds(18, 224, 598, 63); Controls.Add(status);
            profiles.SelectedIndexChanged += delegate { ShowState(); }; mods.SelectedIndexChanged += delegate { ShowState(); };
            storage = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Saber", "RoadCraftGame", "storage");
            game.Text = DetectGame(); Shown += delegate { RefreshLists(); };
        }
        void LabelAt(string text, int x, int y, int width) { var l = new Label { Text = text }; l.SetBounds(x, y, width, 28); Controls.Add(l); }
        void ButtonAt(string text, int x, int y, int width, Action action) { var b = new Button { Text = text }; b.SetBounds(x, y, width, 32); b.Click += delegate { Try(action); }; Controls.Add(b); }
        void Try(Action action) { try { action(); } catch (Exception e) { MessageBox.Show(this, e.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error); } }
        static string DetectGame()
        {
            var candidates = new List<string>();
            foreach (string key in new[] { @"HKEY_CURRENT_USER\Software\Valve\Steam", @"HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Valve\Steam" })
            {
                string steam = Registry.GetValue(key, key.StartsWith("HKEY_CURRENT") ? "SteamPath" : "InstallPath", null) as string;
                if (String.IsNullOrEmpty(steam)) continue;
                candidates.Add(Path.Combine(steam, "steamapps", "common", "RoadCraft"));
                string libraries = Path.Combine(steam, "steamapps", "libraryfolders.vdf");
                if (File.Exists(libraries)) foreach (Match m in Regex.Matches(File.ReadAllText(libraries), "\"path\"\\s*\"([^\"]+)\""))
                    candidates.Add(Path.Combine(m.Groups[1].Value.Replace("\\\\", "\\"), "steamapps", "common", "RoadCraft"));
            }
            candidates.Add(Environment.CurrentDirectory);
            return candidates.FirstOrDefault(p => File.Exists(Path.Combine(p, "root", "bin", "pc", "Roadcraft - Retail.exe"))) ?? "";
        }
        void RefreshLists()
        {
            Try(delegate
            {
                string oldProfile = profiles.SelectedItem as string, oldMod = mods.SelectedItem as string;
                profiles.Items.Clear(); mods.Items.Clear();
                if (Directory.Exists(storage)) profiles.Items.AddRange(Directory.GetFiles(storage, "user_settings.cfg", SearchOption.AllDirectories).OrderByDescending(File.GetLastWriteTimeUtc).Select(p => p.Substring(storage.Length + 1)).ToArray());
                string directory = Path.Combine(game.Text, "root", "mods");
                if (Directory.Exists(directory)) mods.Items.AddRange(Directory.GetFiles(directory, "*.pak").Select(Path.GetFileNameWithoutExtension).OrderBy(x => x).ToArray());
                if (profiles.Items.Count > 0) profiles.SelectedIndex = oldProfile != null && profiles.Items.Contains(oldProfile) ? profiles.Items.IndexOf(oldProfile) : 0;
                if (mods.Items.Count > 0) mods.SelectedIndex = oldMod != null && mods.Items.Contains(oldMod) ? mods.Items.IndexOf(oldMod) : 0;
                ShowState();
            });
        }
        string ProfilePath() { if (profiles.SelectedItem == null) throw new InvalidOperationException("No profile found. Start RoadCraft once, then close it and refresh."); return Path.Combine(storage, (string)profiles.SelectedItem); }
        void ShowState()
        {
            try
            {
                if (profiles.SelectedItem == null) { status.Text = "No retail profile found. Start RoadCraft once, close it, then refresh."; return; }
                var enabled = Settings.Mods(Settings.Text(File.ReadAllBytes(ProfilePath())));
                status.Text = mods.SelectedItem == null ? "No .pak files found. Check the game folder and root\\mods." : ((enabled.Contains("local:" + mods.SelectedItem) ? "Enabled: " : "Disabled: ") + mods.SelectedItem + "\nChanges take effect next time you start RoadCraft.");
            }
            catch (Exception e) { status.Text = e.Message; }
        }
        void Toggle(bool enabled)
        {
            if (mods.SelectedItem == null) throw new InvalidOperationException("Select a mod first.");
            string pak = Path.Combine(game.Text, "root", "mods", mods.SelectedItem + ".pak");
            if (!File.Exists(pak)) throw new FileNotFoundException("The selected .pak is missing. Refresh and try again.");
            string backup = Settings.Update(ProfilePath(), "local:" + mods.SelectedItem, enabled, true);
            ShowState();
            if (backup != null) status.Text += "\nBackup saved beside user_settings.cfg.";
        }
        void Restore()
        {
            string path = ProfilePath(); Settings.RequireClosed();
            using (var d = new OpenFileDialog())
            {
                d.Title = "Choose a settings backup to restore"; d.InitialDirectory = Path.GetDirectoryName(path); d.Filter = "Offline Mods backups|user_settings.cfg.offline-mods-*.bak";
                if (d.ShowDialog(this) != DialogResult.OK) return;
                if (!String.Equals(Path.GetDirectoryName(Path.GetFullPath(d.FileName)), Path.GetDirectoryName(path), StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Choose a backup from this profile's config folder.");
                if (MessageBox.Show(this, "Restore this profile's settings from the selected backup? Your current settings will also be backed up.", Text, MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
                Settings.Write(path, File.ReadAllBytes(path), File.ReadAllBytes(d.FileName), true); ShowState();
            }
        }
        public void Snapshot(string path)
        {
            preview = true; StartPosition = FormStartPosition.Manual; Location = new System.Drawing.Point(-30000, -30000);
            Show(); Application.DoEvents();
            using (var bitmap = new System.Drawing.Bitmap(Width, Height))
            {
                DrawToBitmap(bitmap, new System.Drawing.Rectangle(0, 0, Width, Height));
                bitmap.Save(path, System.Drawing.Imaging.ImageFormat.Png);
            }
            Hide();
        }
    }

    public static class Program
    {
        static void Assert(bool value, string message) { if (!value) throw new Exception("Test failed: " + message); }
        public static string SelfTest(string source, string directory)
        {
            if (Directory.Exists(directory) && Directory.GetFileSystemEntries(directory).Length != 0) throw new IOException("Self-test output must be a new or empty scratch folder.");
            if (String.Equals(Path.GetFullPath(source), Path.GetFullPath(Path.Combine(directory, "user_settings.cfg")), StringComparison.OrdinalIgnoreCase)) throw new IOException("Self-test output must be separate from the input profile.");
            Directory.CreateDirectory(directory);
            byte[] original = File.ReadAllBytes(source), raw = Settings.Decode(original); string text = Settings.Text(original);
            var initial = Settings.Mods(text); int checks = 0;
            foreach (byte codec in new byte[] { 0, 1, 2 }) { Assert(Settings.Decode(Settings.Encode(raw, codec)).SequenceEqual(raw), "codec round trip " + codec); checks++; }
            byte[] boundary = Enumerable.Range(0, 2048).Select(i => (byte)i).ToArray(); Assert(Settings.Transform(Settings.Transform(boundary)).SequenceEqual(boundary), "marker boundaries"); checks++;
            string id = "local:offline_test_" + Guid.NewGuid().ToString("N");
            string added = Settings.Change(text, id, true); Assert(Settings.Mods(added).SequenceEqual(initial.Concat(new[] { id })), "enable preserves existing list"); checks++;
            Assert(Settings.Change(added, id, true) == added, "enable is idempotent"); checks++;
            var oldObject = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(text); var newObject = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(added);
            ((Dictionary<string, object>)oldObject["UserSettings"]).Remove("enabledMods"); ((Dictionary<string, object>)newObject["UserSettings"]).Remove("enabledMods");
            Assert(new JavaScriptSerializer().Serialize(oldObject) == new JavaScriptSerializer().Serialize(newObject), "other settings unchanged"); checks++;
            Assert(Settings.Mods(Settings.Change(added, id, false)).SequenceEqual(initial), "disable restores list"); checks++;
            string missing = "{\"UserSettings\":{\"language\":\"english\",\"nested\":{\"enabledMods\":[]}}}";
            Assert(Settings.Mods(Settings.Change(missing, id, true)).SequenceEqual(new[] { id }), "missing top level list"); checks++;
            string escaped = "{\"UserSettings\":{\"enabledMods\":[\"pros:a]\\\"b\"],\"nested\":{\"enabledMods\":[]}}}";
            Assert(Settings.Mods(Settings.Change(escaped, id, true)).Count == 2, "escaped strings and nested lists"); checks++;
            byte[] corrupt = (byte[])original.Clone(); corrupt[corrupt.Length - 1] ^= 1; bool rejected = false;
            try { Settings.Decode(corrupt); } catch (InvalidDataException) { rejected = true; } Assert(rejected, "bad payload checksum rejected"); checks++;
            byte[] unknown = (byte[])original.Clone(); unknown[52] = 3; rejected = false; try { Settings.Decode(unknown); } catch (InvalidDataException) { rejected = true; } Assert(rejected, "unknown codec rejected"); checks++;
            byte[] badAdler = Settings.Encode(raw, 1); badAdler[badAdler.Length - 1] ^= 1; Array.Copy(Encoding.ASCII.GetBytes(Settings.Hash(badAdler.Skip(53).ToArray())), 0, badAdler, 20, 32);
            rejected = false; try { Settings.Decode(badAdler); } catch (InvalidDataException) { rejected = true; } Assert(rejected, "bad inner checksum rejected"); checks++;
            string copy = Path.Combine(directory, "user_settings.cfg"); File.WriteAllBytes(copy, original);
            string backup = Settings.Update(copy, id, true, false); Assert(File.ReadAllBytes(backup).SequenceEqual(original) && Settings.Mods(Settings.Text(File.ReadAllBytes(copy))).Contains(id), "atomic write and exact backup"); checks++;
            rejected = false; try { Settings.Write(copy, original, Settings.Encode(Encoding.UTF8.GetBytes(added), 2), false); } catch (IOException) { rejected = true; } Assert(rejected, "stale settings rejected"); checks++;
            Settings.Write(copy, File.ReadAllBytes(copy), File.ReadAllBytes(backup), false); Assert(File.ReadAllBytes(copy).SequenceEqual(original), "exact restore"); checks++;
            Assert(Settings.Update(copy, "local:absent_" + Guid.NewGuid().ToString("N"), false, false) == null && File.ReadAllBytes(copy).SequenceEqual(original), "no change leaves bytes untouched"); checks++;
            return checks + " checks passed. Live settings were read only; all writes used " + directory;
        }
        [STAThread]
        public static int Main(string[] args)
        {
            if (args.Length == 3 && args[0] == "--self-test")
            {
                try { string result = SelfTest(args[1], args[2]); File.WriteAllText(Path.Combine(args[2], "test-result.txt"), result); return 0; }
                catch (Exception e) { Directory.CreateDirectory(args[2]); File.WriteAllText(Path.Combine(args[2], "test-result.txt"), e.ToString()); return 1; }
            }
            if (args.Length == 3 && args[0] == "--decode")
            {
                try { if (File.Exists(args[2])) throw new IOException("Decode output already exists."); File.WriteAllText(args[2], Settings.Text(File.ReadAllBytes(args[1])), new UTF8Encoding(false)); return 0; } catch { return 1; }
            }
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            if (args.Length == 2 && args[0] == "--preview") { using (var form = new ModForm()) form.Snapshot(args[1]); return 0; }
            Application.Run(new ModForm()); return 0;
        }
    }
}
