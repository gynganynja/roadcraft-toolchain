// ConsoleTre hub helper for the windowless engine.  See ConsoleTreHub.csproj and library/headless-bench.md.
//
// Usage: roadcraft-consoletre-hub --sdk <SDK>/tools/bin/ModEditor [--port 20563] [--bind 127.0.0.1]
//                                 [--discovery 127.0.0.1|none] [--name <client name>]
//
// stdout/stdin carry JSON lines.  Events: {"event":"ready"|"client_connected"|"client_disconnected"|
// "listener"|"speaker"|"error"|"closed", ...}.  Requests: {"id":n,"op":"ping"|"clients"|"attach"|"exec"|
// "detach"|"close", ...}; every request gets one {"id":n,"ok":true|false,...} line.
//
// What is the SDK's own code (Saber.ConsoleTre.dll, loaded from --sdk at run time):
//  * the hub: new ConsoleServer(addr, port) - what IntegrationStudio runs for AutoStartConsoleTre=Host
//    (EngineConnectorPlugin.cs:142), including framing, SyncTime, pings, passport matching, routing;
//  * the requester: ConsoleClient + SpeakerPassport mirrored from the engine's Automation/ExecSsl
//    listener + ListenerPassport {__PrivateId__ = native GUID text}, request = GUID16 + string(script),
//    reply = one NUL-terminated UTF-8 string - the same calls as integrations/physics-bench/*.ps1.
// What is ours: argument parsing, the JSON-lines framing, the server-side snapshot of clients, and
// rotating the reply GUID after a timeout so that a late reply cannot be read as the next one.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;

namespace RoadCraft.ConsoleTreHub
{
    internal static class Program
    {
        internal static string SdkDir = "";

        private static int Main(string[] args)
        {
            Dictionary<string, string> options;
            try
            {
                options = ParseArgs(args);
            }
            catch (ArgumentException exc)
            {
                Out.Emit(new JsonObject { ["event"] = "error", ["error"] = exc.Message });
                return 2;
            }
            SdkDir = options["sdk"];
            foreach (var dll in new[] { "Saber.ConsoleTre.dll", "Saber.Json.dll" })
            {
                if (!File.Exists(Path.Combine(SdkDir, dll)))
                {
                    Out.Emit(new JsonObject { ["event"] = "error", ["error"] = "missing " + Path.Combine(SdkDir, dll) });
                    return 2;
                }
            }
            AssemblyLoadContext.Default.Resolving += (context, name) =>
            {
                var path = Path.Combine(SdkDir, name.Name + ".dll");
                return File.Exists(path) ? context.LoadFromAssemblyPath(path) : null;
            };
            return Hub.Run(options);  // separate class: SDK types are resolved only after the hook exists
        }

        private static Dictionary<string, string> ParseArgs(string[] args)
        {
            var options = new Dictionary<string, string>
            {
                ["port"] = "20563", ["bind"] = "127.0.0.1", ["discovery"] = "127.0.0.1",
                ["name"] = "RoadCraft headless bench", ["channel"] = "",
            };
            for (int i = 0; i < args.Length; i++)
            {
                if (!args[i].StartsWith("--") || i + 1 >= args.Length)
                    throw new ArgumentException("bad argument " + args[i]);
                options[args[i].Substring(2)] = args[++i];
            }
            if (!options.ContainsKey("sdk"))
                throw new ArgumentException("--sdk <SDK>/tools/bin/ModEditor is required");
            return options;
        }
    }

    internal static class Out
    {
        private static readonly object Lock = new object();
        private static readonly Stream Stdout = Console.OpenStandardOutput();

        public static void Emit(JsonNode node)
        {
            var bytes = Encoding.UTF8.GetBytes(node.ToJsonString() + "\n");
            lock (Lock)
            {
                Stdout.Write(bytes, 0, bytes.Length);
                Stdout.Flush();
            }
        }
    }

    internal static class Hub
    {
        [MethodImpl(MethodImplOptions.NoInlining)]
        public static int Run(Dictionary<string, string> options)
        {
            return new Session(options).Serve();
        }
    }

    internal sealed class Session
    {
        private readonly Dictionary<string, string> _options;
        private readonly int _port;
        private Saber.ConsoleTre.Server.ConsoleServer _server;
        private Saber.ConsoleTre.ConsoleClient _client;
        private Saber.ConsoleTre.ConsoleSpeaker _speaker;
        private Saber.ConsoleTre.ConsoleListener _listener;
        private Saber.ConsoleTre.SpeakerPassport _speakerPassport;
        private string _nativeGuid = "";
        private Guid _requestId;
        private readonly ConcurrentQueue<byte[]> _replies = new ConcurrentQueue<byte[]>();
        private JsonObject _target;

        public Session(Dictionary<string, string> options)
        {
            _options = options;
            _port = int.Parse(options["port"]);
        }

        public int Serve()
        {
            try
            {
                _server = new Saber.ConsoleTre.Server.ConsoleServer(IPAddress.Parse(_options["bind"]), _port);
            }
            catch (Exception exc)
            {
                Out.Emit(new JsonObject
                {
                    ["event"] = "error", ["error"] = "hub could not listen on " + _options["bind"] + ":" + _port,
                    ["detail"] = (exc.InnerException ?? exc).Message,
                });
                return 3;
            }
            _server.ClientConnected += c => Out.Emit(new JsonObject
            {
                ["event"] = "client_connected", ["clientId"] = c.Id, ["name"] = c.ApplicationName,
                ["pid"] = (long)c.ProcessId, ["channel"] = c.Channel,
            });
            _server.ClientDisconnected += (c, reason) => Out.Emit(new JsonObject
            {
                ["event"] = "client_disconnected", ["clientId"] = c.Id, ["name"] = c.ApplicationName,
                ["pid"] = (long)c.ProcessId, ["reason"] = reason,
            });
            _server.ListenerRegistered += (c, l) => Out.Emit(new JsonObject
            {
                ["event"] = "listener", ["clientId"] = c.Id, ["pid"] = (long)c.ProcessId, ["id"] = l.Id,
                ["passport"] = ListenerPassportJson(l.Passport),
            });
            _server.SpeakerRegistered += (c, s) => Out.Emit(new JsonObject
            {
                ["event"] = "speaker", ["clientId"] = c.Id, ["pid"] = (long)c.ProcessId, ["id"] = s.Id,
            });
            if (_options["discovery"] != "none")
                _server.RequestConnect(System.Net.IPAddress.Parse(_options["discovery"]));  // the IPAddress overload, as EngineConnectorPlugin calls it; the string overload builds a DnsEndPoint that Socket.SendTo rejects
            var asm = typeof(Saber.ConsoleTre.ConsoleClient).Assembly;
            Out.Emit(new JsonObject
            {
                ["event"] = "ready", ["port"] = _port, ["bind"] = _options["bind"],
                ["pid"] = Environment.ProcessId, ["protocolVersion"] = Saber.ConsoleTre.ConsoleClient.ProtocolVersion,
                ["consoleTre"] = asm.Location, ["consoleTreVersion"] = asm.GetName().Version?.ToString(),
                ["runtime"] = Environment.Version.ToString(),
            });
            var stdin = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false));
            string line;
            while ((line = stdin.ReadLine()) != null)
            {
                if (line.Trim().Length == 0)
                    continue;
                JsonObject request;
                try
                {
                    request = JsonNode.Parse(line).AsObject();
                }
                catch (Exception exc)
                {
                    Out.Emit(new JsonObject { ["event"] = "error", ["error"] = "bad request: " + exc.Message });
                    continue;
                }
                var id = request["id"]?.DeepClone();
                var op = (string)request["op"] ?? "";
                JsonObject response;
                try
                {
                    response = Dispatch(op, request);
                }
                catch (Exception exc)
                {
                    response = Fail(exc.Message);
                }
                response["id"] = id;
                response["op"] = op;
                Out.Emit(response);
                if (op == "close")
                    return 0;
            }
            Shutdown();
            return 0;
        }

        private JsonObject Dispatch(string op, JsonObject request)
        {
            switch (op)
            {
                case "ping":
                    return Ok();
                case "clients":
                    return Ok(new JsonObject { ["clients"] = Snapshot() });
                case "attach":
                    return Attach(request);
                case "exec":
                    return Exec(request);
                case "detach":
                    Detach();
                    return Ok();
                case "close":
                    Shutdown();
                    Out.Emit(new JsonObject { ["event"] = "closed" });
                    return Ok();
                default:
                    return Fail("unknown op " + op);
            }
        }

        private static JsonObject Ok(JsonObject extra = null)
        {
            var result = extra ?? new JsonObject();
            result["ok"] = true;
            return result;
        }

        private static JsonObject Fail(string error, JsonObject extra = null)
        {
            var result = extra ?? new JsonObject();
            result["ok"] = false;
            result["error"] = error;
            return result;
        }

        private static JsonArray ListenerPassportJson(IEnumerable<Saber.ConsoleTre.ListenerPassport.Condition> passport)
        {
            var array = new JsonArray();
            foreach (var c in passport)
                array.Add(new JsonObject { ["name"] = c.Name, ["value"] = c.Value, ["absent"] = c.ShouldAbsent });
            return array;
        }

        private JsonArray Snapshot()
        {
            var clients = new JsonArray();
            _server.ForEachClient(c =>
            {
                var listeners = new JsonArray();
                foreach (var l in c.Listeners)
                    listeners.Add(new JsonObject { ["id"] = l.Id, ["passport"] = ListenerPassportJson(l.Passport) });
                var speakers = new JsonArray();
                foreach (var s in c.Speakers)
                    speakers.Add(new JsonObject { ["id"] = s.Id });
                clients.Add(new JsonObject
                {
                    ["clientId"] = c.Id, ["name"] = c.ApplicationName, ["pid"] = (long)c.ProcessId,
                    ["channel"] = c.Channel, ["hwnd"] = c.WindowHandle, ["listeners"] = listeners, ["speakers"] = speakers,
                });
            });
            return clients;
        }

        private static bool Has(JsonArray passport, string name, string value) =>
            passport.Any(c => (string)c["name"] == name && (string)c["value"] == value && !(bool)c["absent"]);

        private static string NativeGuid(Guid guid)
        {
            // Native sprintf format: upper case except the third group (prior_notes.md, *.ps1 Get-NativeGuidString).
            var p = guid.ToString("D").Split('-');
            return "{" + p[0].ToUpperInvariant() + "-" + p[1].ToUpperInvariant() + "-" + p[2].ToLowerInvariant() + "-"
                   + p[3].ToUpperInvariant() + "-" + p[4].ToUpperInvariant() + "}";
        }

        private JsonObject Attach(JsonObject request)
        {
            Detach();
            var pids = new HashSet<long>();
            foreach (var p in request["pids"]?.AsArray() ?? new JsonArray())
                pids.Add((long)p);
            double timeout = (double?)request["timeout"] ?? 12.0;
            // Find exactly one client of the engine tree with exactly one Automation/ExecSsl listener.
            var clients = Snapshot();
            var targets = clients.Where(c => pids.Contains((long)c["pid"])).ToList();
            if (targets.Count != 1)
                return Fail("engine pid set does not identify one client", new JsonObject { ["clients"] = clients });
            var target = targets[0].AsObject();
            var inbound = target["listeners"].AsArray()
                .Where(l => Has(l["passport"].AsArray(), "Module", "Automation") && Has(l["passport"].AsArray(), "Type", "ExecSsl"))
                .ToList();
            if (inbound.Count != 1)
                return Fail("engine has no unique Automation/ExecSsl listener", new JsonObject { ["clients"] = clients });
            var passport = inbound[0]["passport"].AsArray();
            var workspace = passport.Where(c => (string)c["name"] == "Workspace" && !(bool)c["absent"]).ToList();
            string channel = (string)target["channel"];
            // Refuse a broadcast: the mirrored passport must reach exactly one listener on that channel.
            int matches = clients.Where(c => (string)c["channel"] == channel)
                .SelectMany(c => c["listeners"].AsArray())
                .Count(l => Has(l["passport"].AsArray(), "Module", "Automation") && Has(l["passport"].AsArray(), "Type", "ExecSsl")
                            && (workspace.Count == 0 || Has(l["passport"].AsArray(), "Workspace", (string)workspace[0]["value"])));
            if (matches != 1)
                return Fail("ambiguous ExecSsl destination; refusing broadcast");
            _client = new Saber.ConsoleTre.ConsoleClient(_options["name"], "127.0.0.1", channel, 0L, _port);
            _client.StartAsync();
            if (!_client.WaitForRegistered(TimeSpan.FromSeconds(timeout)))
            {
                Detach();
                return Fail("registration with the hub timed out");
            }
            _speakerPassport = new Saber.ConsoleTre.SpeakerPassport(false);
            foreach (var c in passport)
                if (!(bool)c["absent"])
                    _speakerPassport.Add((string)c["name"], (string)c["value"]);
            _speaker = _client.CreateSpeaker(_speakerPassport);
            if (!NewReplyListener(timeout))
            {
                Detach();
                return Fail("ExecSsl transport did not connect");
            }
            _target = new JsonObject
            {
                ["clientId"] = target["clientId"]?.DeepClone(), ["pid"] = target["pid"]?.DeepClone(),
                ["name"] = target["name"]?.DeepClone(), ["channel"] = channel, ["listenerId"] = inbound[0]["id"]?.DeepClone(),
                ["passport"] = passport.DeepClone(),
                ["workspace"] = workspace.Count == 1 ? (string)workspace[0]["value"] : null,
            };
            return Ok(new JsonObject { ["target"] = _target.DeepClone(), ["requestId"] = _nativeGuid });
        }

        private bool NewReplyListener(double timeout)
        {
            if (_listener != null)
            {
                _client.DestroyListener(_listener);
                _listener = null;
            }
            while (_replies.TryDequeue(out _)) { }
            _requestId = Guid.NewGuid();
            _nativeGuid = NativeGuid(_requestId);
            var lp = new Saber.ConsoleTre.ListenerPassport(false);
            lp.Add("__PrivateId__", _nativeGuid);
            _listener = _client.CreateListener(lp);
            _listener.ReceiveMessage += (listener, message) =>
            {
                var stream = message.GetReadStream();
                _replies.Enqueue(new Saber.ConsoleTre.NativeReader(stream, true).ReadBytes((int)stream.Length));
            };
            var deadline = DateTime.UtcNow.AddSeconds(timeout);
            while ((!_speaker.HasConnectedListeners || !_listener.IsRegistered) && DateTime.UtcNow < deadline)
                Thread.Sleep(10);
            return _speaker.HasConnectedListeners && _listener.IsRegistered;
        }

        private JsonObject Exec(JsonObject request)
        {
            if (_speaker == null)
                return Fail("not attached");
            string script = (string)request["script"] ?? "";
            double timeout = (double?)request["timeout"] ?? 12.0;
            if (!_speaker.HasConnectedListeners)
                return Fail("engine listener disconnected");
            while (_replies.TryDequeue(out _)) { }
            var message = new Saber.ConsoleTre.UserMessage();
            var writer = message.Write();
            writer.Write(_requestId.ToByteArray());
            writer.Write(script, false);
            var started = DateTime.UtcNow;
            if (!_speaker.Send(message))
                return Fail("transport rejected request");
            var deadline = started.AddSeconds(timeout);
            byte[] raw = null;
            while (!_replies.TryDequeue(out raw) && DateTime.UtcNow < deadline)
                Thread.Sleep(2);
            double ms = (DateTime.UtcNow - started).TotalMilliseconds;
            if (raw == null)
            {
                // A late reply to this GUID must not be taken for the next request's reply.
                bool rotated = NewReplyListener(Math.Min(timeout, 5.0));
                return Fail("timeout", new JsonObject { ["ms"] = ms, ["rotated"] = rotated, ["requestId"] = _nativeGuid });
            }
            if (raw.Length < 1 || raw[raw.Length - 1] != 0 || Array.IndexOf(raw, (byte)0) != raw.Length - 1)
                return Fail("unexpected reply framing", new JsonObject { ["ms"] = ms, ["bytes"] = raw.Length });
            string text;
            try
            {
                text = new UTF8Encoding(false, true).GetString(raw, 0, raw.Length - 1);
            }
            catch (DecoderFallbackException)
            {
                return Fail("reply is not UTF-8", new JsonObject { ["ms"] = ms, ["bytes"] = raw.Length });
            }
            return Ok(new JsonObject { ["reply"] = text, ["ms"] = ms, ["bytes"] = raw.Length });
        }

        private void Detach()
        {
            if (_client == null)
                return;
            try
            {
                if (_speaker != null)
                    _client.DestroySpeaker(_speaker);
                if (_listener != null)
                    _client.DestroyListener(_listener);
                _client.Close();
            }
            catch (Exception)
            {
            }
            _client = null;
            _speaker = null;
            _listener = null;
            _target = null;
        }

        private void Shutdown()
        {
            Detach();
            try
            {
                _server?.Close();
            }
            catch (Exception)
            {
            }
            _server = null;
        }
    }
}
