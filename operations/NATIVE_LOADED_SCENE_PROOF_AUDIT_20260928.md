# Loaded-scene and capture-origin API audit (2026-09-28)

The current D11 capture contract correctly leaves `loadedSceneVerified` and
`captureProcessAuthenticated` false. This read-only audit looked for a native
scene identity stronger than a path in the runner's `open` command or
`EngineControl.GetLevelName()`. It did not launch the editor or Painter, send
SSL, create a screenshot, or change an accepted scene, PAK, or receipt.

## Pinned evidence and what it says

The installed `root/bin/pc/Roadcraft ModEditor.exe` is 126,773,216 bytes,
SHA-256 `ce6a48b1c73bea0876376d3251a6810b4a9913a7d500226e42bb2c605f3810b7`.
Its ASCII SSL name table contains these adjacent entries (file offsets):

| Binding/name | Offset | Interpretation limited to the evidence |
| --- | ---: | --- |
| `EngineControl`, `LoadLevel`, `GetLevelName` | `0x05244a38`, `0x05244a60`, `0x05244a98` | Candidate runtime level label. The five-probe transport already covers `GetLevelName`, but its SSL signature and result remain untested. A label cannot identify source bytes. |
| `iactor`, `GetSceneName` | `0x05072018`, `0x050720c8` | Candidate scene-name property of an editor actor, not a getter for the active scene's resource digest. No scoped actor query or return shape has been demonstrated. |
| `GameEditor`, `FindGameObjectByName`, `GetGameObjects`, `GetSceneBbox` | `0x05073ad8`, `0x05073b50`, `0x05073cb0`, `0x05073c88` | Candidate editor-object inspection surface. The name table alone does not establish a callable global, method signatures, which scene(s) are enumerated, or loaded-byte identity. |

An exact ASCII scan of this pinned executable found `GetActiveScene` only in
an RTTI type name (`scnGetActiveSceneErrorLog`, offset `0x073cffa1`), not in an
observed SSL method table. It found no literal `GetSceneGuid`, `GetSceneGUID`,
`GetSourcePath`, or `GetSourceInfo`. This is a bounded negative search, **not**
proof that the engine has no other internal API or logging channel. The
shipped `D11_Full_Rig_Audit_20260925/native/sdk_sources/` SSL source is three
animation/controller files and provides no working call to these scene
identity methods.

The maintained runner `D11_Interior_AAA_20260928/capture_candidate_native.py`
(SHA-256 `6449ddc08c81165231ee39f90e171b2f5a2c7fdecc9e2e21b1b2c1b2d4733585`)
writes a scenario that opens the selected `.scn`, waits for scene loading, and
checks a ready marker and the process's `mods_source` resource mount. The
maroon source `.scn` currently hashes to
`9481bca1db96dd5c3c0c201f9d7f84e0b16fd7e683905c286060b16e9d53dfa1`.
Those are command, process-log, mount, and **on-disk** source facts. They do
not report which resource bytes the renderer actually loaded.

The historical generated capture helper
`native/runs/aaa_maroon_bd58bce0ma/native_controls.ps1` (under
`D11_Interior_AAA_20260928`, SHA-256
`febe294bc940ca53bbbe0a0850dfc1bb75358fdc72ba196ed609a7e32241a975`)
issues `SaveScreenshot` with a named target, then constructs its reply. The
current runner checks a new screenshot target, copies the resulting PNG, and
hashes it. `native_capture_partial` binds the request, response, action
windows, process ID, helper, scene-source hash, and PNG consistently. The
reply is post-trigger and contains neither an engine-reported loaded-scene
digest nor an engine-reported PNG digest. The receipt chain is useful
consistency evidence; it is not independent authentication of the producer.

## Managed editor bridge boundary

A metadata-only inspection of the shipped .NET editor plugins (no assemblies
executed) gives a more exact boundary than the native name table alone:

| Pinned plugin SHA-256 | Relevant metadata and method body | Consequence |
| --- | --- | --- |
| `EngineConnectorPlugin.dll`: `a9b943a9c3be496631ef7b1c2181b9b450043f414cf188615618fe369d836d48` | `GameInformation.LoadedScene`, `IEngineConnectionManager.LoadedScene`, and `ConsoleConnectionManager.LoadedScene` are `System.String`. `ConsoleConnectionManager.ReceiveSceneName(TreEngineMessage)` calls `ReadString` and `set_LoadedScene`. | The engine-to-editor loaded-scene notification conveys a name, not loaded resource bytes or a digest. |
| `XginePlugin.dll`: `010dcc1affd73c7b24321ff0f75db3aa0b22a27cbd04499bc9ac8217c270b4f8` | `XgineViewportSceneLoadData.SceneName` and `.SceneData` are `System.String`. `GameEditor.LoadScene` writes both strings and serialized resource data (`SaveToString`) into a `LoadScene`/`LoadScenePlay` engine message. `GameEditor.CurrentScene` is `System.String`. | The editor can identify the payload it *sent*, but the subsequent name notification does not attest to which resource bytes the engine retained or rendered. |
| `XgineMovieMakerPlugin.dll`: `f1af2e361091d8b4abc48e163121e38876cfc703ce8741ee88c6097b5a226741` | `CinematicConnection.SendTakeScreenShot(System.String)` returns `void`; its method body writes a `CinematicTakeScreenShot` command and target string, then sends the message. | This second screenshot command path also has no PNG-byte acknowledgement in its public method contract. |
| `EngineViewportPlugin.dll`: `c045ada12dcba0d2bb9009fb25685acd43f831ec410b492dc41d6a6ac4693c51` | `EnginePreviewProvider.ProcessImage(System.String)` calls `File.ReadAllBytes`. `SafeD3D11Device.GetTextureSubresourceData` reads a mapped texture into `SubresourceData[]`. | The preview API reads an existing image file, while the shared-texture helper concerns pixels rather than the exact `SaveScreenshot` PNG bytes. Neither is a demonstrated SSL scene-digest or screenshot-digest reply. |

These are exact type and IL call observations for the pinned DLLs, not a claim
that no hidden native interface exists. The installed native executable has no
literal `GetSceneHash`, `GetSceneChecksum`, `GetFileHash`, `HashFile`,
`ComputeHash`, or `GetLoadedScene` string. Its `GetCurrentSceneUid` occurrences
are internal `net_scene_protocol.cpp` diagnostic expressions rather than a
demonstrated SSL binding. A native resource UID would still need a proven map
to the pinned resource bytes. The editor's managed `GameViewportSettings`
exposes ambient and lighting configuration getters, but they are not
capture-time engine readback of the actual rendered state.

An implementable proof bridge would need a **new demonstrated engine-side
read-only response** on the same owned process/session: immediately after a
scene-load completion it would report the resource identifier, byte count,
and SHA-256 over the actual scene resource buffer consumed by the engine;
after `SaveScreenshot` completes it would report the exact target, byte count,
and SHA-256 over the completed PNG bytes (or supply those bytes directly).
Bind both replies to a fresh host nonce, the pinned process identity, request
ID, variant/view, and time interval. Independently hash the source or compiled
resource selected for that load and the resulting PNG, then compare. The
payload sent by the editor, a received scene name, OS file access, and a host
hash of a PNG are useful cross-checks, but cannot substitute for either
engine-side measurement. No such callable response has been established in
the shipped SDK or current transport, so this is a specification, not an
implemented proof or permission to set either gate true.

### Reproducing the managed metadata inspection

The observations above came from PowerShell 7.6.5 and its .NET
System.Reflection.Metadata APIs. The plugin DLLs were opened as PE metadata;
the plugins themselves were **not** loaded or executed. First recheck the four
SHA-256 values in the table. For member signatures, load the shipped
System.Reflection.MetadataLoadContext.dll from the ModEditor directory and use
MetadataLoadContext.LoadFromAssemblyPath; this returned System.String for the
three LoadedScene getters, SceneName, SceneData, and CurrentScene, and
System.Void for SendTakeScreenShot(System.String).

Run the SHA/IL block below first, then run this separate no-execute
signature check in the same PowerShell session. It prints the concrete
method signatures:

~~~powershell
Add-Type -Path (Join-Path $base 'System.Reflection.MetadataLoadContext.dll')
$assemblyPaths = @((Get-ChildItem $PSHOME -Filter '*.dll' -File).FullName) +
  @((Get-ChildItem $base -Filter '*.dll' -File).FullName) +
  @((Get-ChildItem (Join-Path $base 'Plugins') -Filter '*.dll' -File).FullName)
$context = [System.Reflection.MetadataLoadContext]::new(
  [System.Reflection.PathAssemblyResolver]::new([string[]]$assemblyPaths))
$signatures = @(
  @('EngineConnectorPlugin.dll','GameInformation','get_LoadedScene'),
  @('EngineConnectorPlugin.dll','IEngineConnectionManager','get_LoadedScene'),
  @('EngineConnectorPlugin.dll','ConsoleConnectionManager','get_LoadedScene'),
  @('XginePlugin.dll','XgineViewportSceneLoadData','get_SceneName'),
  @('XginePlugin.dll','XgineViewportSceneLoadData','get_SceneData'),
  @('XginePlugin.dll','GameEditor','get_CurrentScene'),
  @('XgineMovieMakerPlugin.dll','CinematicConnection','SendTakeScreenShot'),
  @('EngineViewportPlugin.dll','SafeD3D11Device','GetTextureSubresourceData'),
  @('EngineViewportPlugin.dll','EnginePreviewProvider','ProcessImage')
)
try {
  foreach ($spec in $signatures) {
    $path = Join-Path $base ('Plugins\' + $spec[0])
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -cne $pins[$spec[0]]) { throw "DLL changed: $($spec[0])" }
    $assembly = $context.LoadFromAssemblyPath($path)
    $type = $assembly.GetTypes() | Where-Object Name -CEQ $spec[1] |
      Select-Object -First 1
    if (-not $type) { throw "Missing type: $($spec[1])" }
    $methods = $type.GetMethods(
      [Reflection.BindingFlags]'Public,NonPublic,Instance,Static,DeclaredOnly') |
      Where-Object Name -CEQ $spec[2]
    if (-not $methods) { throw "Missing method: $($spec[2])" }
    foreach ($method in $methods) {
      '{0}: {1}.{2}' -f $spec[0],$spec[1],$method.ToString()
    }
  }
} finally { $context.Dispose() }
~~~

For the method-body assertions, PEReaderExtensions.GetMetadataReader and
GetMethodBody supplied raw IL. Decode at instruction boundaries using
System.Reflection.Emit.OpCodes operand widths, then resolve InlineMethod and
InlineString tokens through MetadataTokens and MetadataReader. On these exact
pinned DLLs the decisive instructions are:

| DLL / method | IL offset, opcode, resolved operand |
| --- | --- |
| EngineConnectorPlugin / ConsoleConnectionManager.ReceiveSceneName | 0x0001 callvirt ReadString; 0x0032 callvirt set_LoadedScene |
| XginePlugin / GameEditor.LoadScene | 0x000a ldstr LoadScene; 0x0011 ldstr LoadScenePlay; 0x001c callvirt get_SceneName; 0x0027 callvirt get_SceneData; 0x0050 callvirt SaveToString; 0x019c callvirt Send |
| XgineMovieMakerPlugin / CinematicConnection.SendTakeScreenShot | 0x0007 ldstr CinematicTakeScreenShot; 0x0014 callvirt Write; 0x001b callvirt Send |
| EngineViewportPlugin / EnginePreviewProvider.ProcessImage | 0x0008 call ReadAllBytes |

This compact read-only PowerShell check resolves those exact operands from
metadata, refusing any changed DLL before inspection:

~~~powershell
$base = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\ModEditor'
$pins = @{
  'EngineConnectorPlugin.dll'='a9b943a9c3be496631ef7b1c2181b9b450043f414cf188615618fe369d836d48'
  'XginePlugin.dll'='010dcc1affd73c7b24321ff0f75db3aa0b22a27cbd04499bc9ac8217c270b4f8'
  'XgineMovieMakerPlugin.dll'='f1af2e361091d8b4abc48e163121e38876cfc703ce8741ee88c6097b5a226741'
  'EngineViewportPlugin.dll'='c045ada12dcba0d2bb9009fb25685acd43f831ec410b492dc41d6a6ac4693c51'
}
$checks = @(
  @('EngineConnectorPlugin.dll','ConsoleConnectionManager','ReceiveSceneName',@(0x0001,0x0032)),
  @('XginePlugin.dll','GameEditor','LoadScene',@(0x000a,0x0011,0x001c,0x0027,0x0050,0x019c)),
  @('XgineMovieMakerPlugin.dll','CinematicConnection','SendTakeScreenShot',@(0x0007,0x0014,0x001b)),
  @('EngineViewportPlugin.dll','EnginePreviewProvider','ProcessImage',@(0x0008))
)
foreach ($spec in $checks) {
  $path = Join-Path $base ('Plugins\' + $spec[0])
  $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($hash -cne $pins[$spec[0]]) { throw "DLL changed: $($spec[0])" }
  $stream = [IO.File]::OpenRead($path)
  try {
    $pe = [System.Reflection.PortableExecutable.PEReader]::new($stream)
    $md = [System.Reflection.Metadata.PEReaderExtensions]::GetMetadataReader($pe)
    $found = $false
    foreach ($typeHandle in $md.TypeDefinitions) {
      $type = $md.GetTypeDefinition($typeHandle)
      if ($md.GetString($type.Name) -cne $spec[1]) { continue }
      foreach ($methodHandle in $type.GetMethods()) {
        $method = $md.GetMethodDefinition($methodHandle)
        if ($md.GetString($method.Name) -cne $spec[2]) { continue }
        $found = $true
        $il = [System.Reflection.Metadata.PEReaderExtensions]::GetMethodBody(
          $pe, $method.RelativeVirtualAddress).GetILBytes()
        foreach ($offset in $spec[3]) {
          $opcode = [int]$il[$offset]
          if ($opcode -notin @(0x28,0x6f,0x72)) { throw "Unexpected opcode at $offset" }
          $token = [BitConverter]::ToInt32($il, $offset + 1)
          if ($opcode -eq 0x72) {
            $handle = [System.Reflection.Metadata.Ecma335.MetadataTokens]::UserStringHandle(
              $token -band 0x00ffffff)
            $name = $md.GetUserString($handle)
          } else {
            $handle = [System.Reflection.Metadata.Ecma335.MetadataTokens]::EntityHandle($token)
            $name = switch ($handle.Kind) {
              'MethodDefinition' { $md.GetString($md.GetMethodDefinition($handle).Name) }
              'MemberReference' { $md.GetString($md.GetMemberReference($handle).Name) }
              default { throw "Unexpected token kind at $offset" }
            }
          }
          '{0}: {1}.{2} 0x{3:x4} {4}' -f $spec[0],$spec[1],$spec[2],$offset,$name
        }
      }
    }
    if (-not $found) { throw "Missing method: $($spec[1]).$($spec[2])" }
  } finally { $stream.Dispose() }
}
~~~

The pinned instruction offsets avoid interpreting arbitrary operand bytes as
opcodes; they are valid only while the DLL hashes above match. The separate
MetadataLoadContext signature check establishes the types of the named
properties and methods. This inspection does not test a live editor session.

## OS trace boundary

The installed `C:\Windows\system32\wpr.exe` lists a `FileIO` profile. Its
`FileIO.Verbose` profile details include process/thread events and file create,
read, write, and rename events. `tracerpt.exe` is installed; `wpa.exe` and
`WPAExporter.exe` were not found on `PATH` or in the standard Windows
Performance Toolkit locations. [Microsoft's WPR profile documentation](https://learn.microsoft.com/en-us/windows-hardware/test/wpt/built-in-recording-profiles),
[WPA graph list](https://learn.microsoft.com/en-us/windows-hardware/test/wpt/list-of-wpa-graphs),
and [tracerpt reference](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/tracerpt)
describe the available file-I/O recording and parsing surfaces. No trace was
started for this audit.

A future, bounded FileIO trace could corroborate that a particular process
accessed a scene path or wrote a PNG path during a capture interval. File-I/O
events do not record the bytes or SHA-256 of a loaded resource, identify the
scene the renderer actually used, or authenticate the rendered image's origin.
Even a matching PID/path/time trace would be supporting process evidence, not
grounds to set `loadedSceneVerified` or `captureProcessAuthenticated` true.

## Next native experiment and acceptance rule

The shortest currently available method smoke is the exact pinned
`level_name` fragment from `operations/probes/d11_level_name.ssl`. Its
offline preflight is `python -B -m roadcraft.native_probe_transport --kind
level_name --variant maroon` with this checkout's `src` on `PYTHONPATH`.
Only later, in an already-open **disposable** editor session after its
validation scene and active viewport have loaded, use the same command with
`--execute --engine-pid <exact-pid> --output
<absolute-new-file-under-local/native-probes>`.
The transport must match the pinned executable path/hash, process start time,
one ConsoleTre client in that PID, one `Automation/ExecSsl` listener, and one
workspace. A separately recorded owner/parent process and retained handle
would be needed to prove session ownership; this standalone transport checks
identity, but does not itself prove ownership or loaded-scene bytes. Preserve
the raw request, native reply or compilation error,
request/response times, and the new receipt; compare the result with the
editor's visible scene tab and any engine loaded-scene notification. This
tests only whether the method compiles and what label it returns. It cannot
resolve the byte or PNG origin gate even when all labels agree. The other four
existing fragments can follow independently for camera and lighting
diagnostics. The independent actor/editor names above
are **not** executable probes yet: establish a demonstrated SSL global,
signature, scope, and null behavior before adding any transport fragment.

For `loadedSceneVerified: true`, require native evidence bound to the same
process and capture interval that identifies the loaded validation resource
and links it to the exact pinned scene source or compiled resource bytes.
A matching level or actor label, scenario command, mounted source directory,
and on-disk SHA do not meet that rule separately or together. For
`captureProcessAuthenticated: true`, require an independently verified
engine-origin response bound to the exact screenshot request and image bytes,
in addition to the existing action/PNG hash chain. Keep both fields false and
keep the baseline/candidate pair gate blocked until those native proofs and
complete renderer readback have been demonstrated and reviewed.
