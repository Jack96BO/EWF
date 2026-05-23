Imports System.Management
Imports System.IO
Imports System.Threading.Tasks
Imports System.Net.Http
Imports System.Text
Imports System.Text.Json
Imports System.Collections.Generic
Imports System.Windows
Imports System.Windows.Controls
Imports Microsoft.Win32

Public Class DiskBackupControl
    Inherits UserControl

    Private ReadOnly _httpClient As HttpClient = New HttpClient()

    Private Class EndpointItem
        Public Property Metodo As String
        Public Property Path As String

        Public Overrides Function ToString() As String
            Return $"{Metodo} {Path}"
        End Function
    End Class

    Public Sub New()
        InitializeComponent()
        AddHandler Loaded, AddressOf DiskBackupControl_Load
        AddHandler Button1.Click, AddressOf Button1_Click
        AddHandler Button2.Click, AddressOf Button2_Click
        AddHandler Button3.Click, AddressOf Button3_Click
        AddHandler ButtonHealth.Click, AddressOf ButtonHealth_Click
        AddHandler ButtonMenu.Click, AddressOf ButtonMenu_Click
        AddHandler ButtonExecuteEndpoint.Click, AddressOf ButtonExecuteEndpoint_Click
        AddHandler ButtonRawApi.Click, AddressOf ButtonRawApi_Click
        AddHandler ButtonRawCpp.Click, AddressOf ButtonRawCpp_Click
        AddHandler ButtonRawCppBrowseDll.Click, AddressOf ButtonRawCppBrowseDll_Click
        AddHandler ButtonRawCppAutoDetectDll.Click, AddressOf ButtonRawCppAutoDetectDll_Click
        AddHandler ButtonPresetEwfInfo.Click, AddressOf ButtonPresetEwfInfo_Click
        AddHandler ButtonPresetEwfAcquire.Click, AddressOf ButtonPresetEwfAcquire_Click
        AddHandler ButtonPresetEwfAcquireStream.Click, AddressOf ButtonPresetEwfAcquireStream_Click
        AddHandler ButtonPresetEwfRawCopy.Click, AddressOf ButtonPresetEwfRawCopy_Click
        AddHandler ButtonPresetEwfRawCopyCpp.Click, AddressOf ButtonPresetEwfRawCopyCpp_Click
        AddHandler ButtonPresetEwfExport.Click, AddressOf ButtonPresetEwfExport_Click
        AddHandler ButtonPresetEwfVerify.Click, AddressOf ButtonPresetEwfVerify_Click
        AddHandler ButtonPresetEwfRecover.Click, AddressOf ButtonPresetEwfRecover_Click
        AddHandler ButtonPresetEwfMount.Click, AddressOf ButtonPresetEwfMount_Click
        AddHandler ButtonPresetEwfUnmount.Click, AddressOf ButtonPresetEwfUnmount_Click
        AddHandler ButtonPresetEwfMounts.Click, AddressOf ButtonPresetEwfMounts_Click
        AddHandler ButtonPresetEwfDebug.Click, AddressOf ButtonPresetEwfDebug_Click
        AddHandler ButtonPresetReadInfo.Click, AddressOf ButtonPresetReadInfo_Click
        AddHandler ButtonPresetReadLs.Click, AddressOf ButtonPresetReadLs_Click
        AddHandler ButtonPresetReadTree.Click, AddressOf ButtonPresetReadTree_Click
        AddHandler ButtonPresetReadCat.Click, AddressOf ButtonPresetReadCat_Click
        AddHandler ButtonPresetReadExtract.Click, AddressOf ButtonPresetReadExtract_Click
    End Sub

    Private Sub DiskBackupControl_Load(sender As Object, e As RoutedEventArgs)
        CaricaDischi()
        InizializzaEndpointMenu()
        AutoImpostaDllPath()
        TextBoxPayload.Text = "{}"
    End Sub

    Private Sub InizializzaEndpointMenu()
        ComboBoxEndpointSelector.Items.Clear()
        Dim endpoints As EndpointItem() = {
            New EndpointItem With {.Metodo = "POST", .Path = "/ewf/info"},
            New EndpointItem With {.Metodo = "POST", .Path = "/ewf/acquire"},
            New EndpointItem With {.Metodo = "POST", .Path = "/ewf/acquire-stream"},
            New EndpointItem With {.Metodo = "POST", .Path = "/ewf/rawCopyXsector"},
            New EndpointItem With {.Metodo = "POST", .Path = "/ewf/rawCopyXsectorCpp"},
            New EndpointItem With {.Metodo = "POST", .Path = "/ewf/export"},
            New EndpointItem With {.Metodo = "POST", .Path = "/ewf/verify"},
            New EndpointItem With {.Metodo = "POST", .Path = "/ewf/recover"},
            New EndpointItem With {.Metodo = "POST", .Path = "/ewf/mount"},
            New EndpointItem With {.Metodo = "POST", .Path = "/ewf/unmount"},
            New EndpointItem With {.Metodo = "GET", .Path = "/ewf/mounts"},
            New EndpointItem With {.Metodo = "POST", .Path = "/ewf/debug"},
            New EndpointItem With {.Metodo = "POST", .Path = "/read/info"},
            New EndpointItem With {.Metodo = "POST", .Path = "/read/ls"},
            New EndpointItem With {.Metodo = "POST", .Path = "/read/tree"},
            New EndpointItem With {.Metodo = "POST", .Path = "/read/cat"},
            New EndpointItem With {.Metodo = "POST", .Path = "/read/extract"}
        }

        For Each item In endpoints
            ComboBoxEndpointSelector.Items.Add(item)
        Next

        If ComboBoxEndpointSelector.Items.Count > 0 Then
            ComboBoxEndpointSelector.SelectedIndex = 0
        End If
    End Sub

    Private Sub CaricaDischi()
        ComboBox1.Items.Clear()

        Try
            Dim searcher As New ManagementObjectSearcher("SELECT DeviceID, Model, Size FROM Win32_DiskDrive")

            For Each wmiObject As ManagementObject In searcher.Get()
                Dim deviceId As String = wmiObject("DeviceID").ToString()
                Dim model As String = wmiObject("Model").ToString()
                Dim size As Long = Convert.ToInt64(wmiObject("Size"))

                Dim itemText As String = $"{deviceId} - {model} ({FormatSize(size)})"
                ComboBox1.Items.Add(itemText)
            Next

            If ComboBox1.Items.Count > 0 Then ComboBox1.SelectedIndex = 0
        Catch ex As Exception
            MessageBox.Show("Errore nella scansione dei dischi: " & ex.Message, "Errore", MessageBoxButton.OK, MessageBoxImage.Error)
        End Try
    End Sub

    Private Function FormatSize(size As Long) As String
        Return $"{Math.Round(size / 1024.0 / 1024.0 / 1024.0, 2)} GB"
    End Function

    Private Function GetApiBaseUrl() As String
        Dim baseUrl = TextBoxApiBase.Text.Trim()
        If String.IsNullOrWhiteSpace(baseUrl) Then
            baseUrl = "http://127.0.0.1:9901"
        End If
        Return baseUrl.TrimEnd("/"c)
    End Function

    Private Async Function GetEndpointAsync(path As String) As Task
        Dim url = GetApiBaseUrl() & path
        Try
            Dim response = Await _httpClient.GetAsync(url)
            Dim content = Await response.Content.ReadAsStringAsync()
            Log($"GET {path} -> HTTP {CInt(response.StatusCode)}")
            Log(content)
        Catch ex As Exception
            Log($"Errore chiamata GET {path}: {ex.Message}")
        End Try
    End Function

    Private Async Function PostEndpointWithResultAsync(path As String, jsonPayload As String) As Task(Of Boolean)
        Dim url = GetApiBaseUrl() & path
        Try
            Dim content = New StringContent(jsonPayload, Encoding.UTF8, "application/json")
            Dim response = Await _httpClient.PostAsync(url, content)
            Dim responseText = Await response.Content.ReadAsStringAsync()
            Log($"POST {path} -> HTTP {CInt(response.StatusCode)}")
            Log(responseText)

            Dim isSuccess As Boolean = response.IsSuccessStatusCode
            Try
                Using doc = JsonDocument.Parse(responseText)
                    Dim root = doc.RootElement
                    Dim successElement As JsonElement
                    If root.TryGetProperty("success", successElement) Then
                        isSuccess = successElement.GetBoolean()
                    End If
                End Using
            Catch
                ' keep HTTP status based result when response is not JSON
            End Try

            Return isSuccess
        Catch ex As Exception
            Log($"Errore chiamata POST {path}: {ex.Message}")
            Return False
        End Try
    End Function

    Private Async Function PostEndpointAsync(path As String, jsonPayload As String) As Task
        Await PostEndpointWithResultAsync(path, jsonPayload)
    End Function

    Private Function GetSelectedSourceDisk() As String
        If ComboBox1.SelectedItem Is Nothing Then
            Return ""
        End If
        Return ComboBox1.SelectedItem.ToString().Split(" "c)(0)
    End Function

    Private Function BuildRawCopyPayload() As String
        Dim sourceDisk = GetSelectedSourceDisk()
        Dim outputPath = TextBoxFilePath.Text.Trim()

        Dim bytesPerSector As Integer = 512
        Integer.TryParse(TextBoxRawBytesPerSector.Text.Trim(), bytesPerSector)

        Dim startSector As Integer = 0
        Integer.TryParse(TextBoxRawStartSector.Text.Trim(), startSector)

        Dim bufferSectors As Integer = 2048
        Integer.TryParse(TextBoxRawBufferSectors.Text.Trim(), bufferSectors)

        Dim sectorCountStr = TextBoxRawSectorCount.Text.Trim()
        Dim forceVal = CheckBoxRawForce.IsChecked = True
        Dim verboseVal = CheckBoxRawVerbose.IsChecked = True

        If String.IsNullOrWhiteSpace(sectorCountStr) Then
            Return $"{{""source"":""{EscapeJson(sourceDisk)}"",""output"":""{EscapeJson(outputPath)}"",""bytes_per_sector"":{bytesPerSector},""start_sector"":{startSector},""buffer_sectors"":{bufferSectors},""force"":{forceVal.ToString().ToLowerInvariant()},""verbose"":{verboseVal.ToString().ToLowerInvariant()}}}"
        End If

        Dim sectorCount As Integer = 0
        Integer.TryParse(sectorCountStr, sectorCount)
        Return $"{{""source"":""{EscapeJson(sourceDisk)}"",""output"":""{EscapeJson(outputPath)}"",""bytes_per_sector"":{bytesPerSector},""start_sector"":{startSector},""sector_count"":{sectorCount},""buffer_sectors"":{bufferSectors},""force"":{forceVal.ToString().ToLowerInvariant()},""verbose"":{verboseVal.ToString().ToLowerInvariant()}}}"
    End Function

    Private Function BuildRawCppPayload() As String
        Dim sourceDisk = GetSelectedSourceDisk()
        Dim outputPath = TextBoxFilePath.Text.Trim()
        Dim dllPath = TextBoxRawCppDllPath.Text.Trim()

        If String.IsNullOrWhiteSpace(dllPath) Then
            Return $"{{""source"":""{EscapeJson(sourceDisk)}"",""output"":""{EscapeJson(outputPath)}""}}"
        End If

        Return $"{{""source"":""{EscapeJson(sourceDisk)}"",""output"":""{EscapeJson(outputPath)}"",""dll_path"":""{EscapeJson(dllPath)}""}}"
    End Function

    Private Function EscapeJson(value As String) As String
        Return value.Replace("\", "\\").Replace("""", "\""")
    End Function

    Private Function FindRawCopyDllPath() As String
        Dim candidates As New List(Of String)()
        Dim envDll = Environment.GetEnvironmentVariable("RAWCOPYXSECTOR_DLL")
        If Not String.IsNullOrWhiteSpace(envDll) Then
            candidates.Add(envDll)
        End If

        Dim baseDir = AppDomain.CurrentDomain.BaseDirectory
        candidates.Add(Path.Combine(baseDir, "rawCopyXsector.dll"))
        candidates.Add(Path.Combine(baseDir, "rawCopyXsector", "rawCopyXsector", "x64", "Release", "rawCopyXsector.dll"))
        candidates.Add(Path.Combine(baseDir, "rawCopyXsector", "rawCopyXsector", "x64", "Debug", "rawCopyXsector.dll"))

        Dim cwd = Directory.GetCurrentDirectory()
        candidates.Add(Path.Combine(cwd, "rawCopyXsector", "rawCopyXsector", "x64", "Release", "rawCopyXsector.dll"))
        candidates.Add(Path.Combine(cwd, "rawCopyXsector", "rawCopyXsector", "x64", "Debug", "rawCopyXsector.dll"))

        For Each candidate In candidates
            If Not String.IsNullOrWhiteSpace(candidate) AndAlso File.Exists(candidate) Then
                Return candidate
            End If
        Next

        Return ""
    End Function

    Private Sub AutoImpostaDllPath()
        Dim detected = FindRawCopyDllPath()
        If Not String.IsNullOrWhiteSpace(detected) Then
            TextBoxRawCppDllPath.Text = detected
            Log($"DLL RawCopyXsector trovata automaticamente: {detected}")
        End If
    End Sub

    Private Function BuildPresetPayload(path As String) As String
        Select Case path
            Case "/ewf/info"
                Return "{""images"" : [""/cases/disk.E01""], ""verbose"": true}"
            Case "/ewf/acquire"
                Return "{""source"": ""\\\\.\\PhysicalDrive1"", ""target"": ""C:/evidence/case001/disk"", ""format"": ""ewf"", ""compression"": ""fast"", ""no_prompt"": true}"
            Case "/ewf/acquire-stream"
                Return "{""input"": ""/images/disk.raw"", ""target"": ""/evidence/disk"", ""compression"": ""best"", ""no_prompt"": true}"
            Case "/ewf/rawCopyXsector"
                Return "{""source"": ""/images/disk.raw"", ""output"": ""/exports/slice.raw"", ""bytes_per_sector"": 512, ""start_sector"": 0, ""sector_count"": 2048, ""force"": true}"
            Case "/ewf/rawCopyXsectorCpp"
                Return "{""source"": ""\\\\.\\PhysicalDrive1"", ""output"": ""C:/evidence/fallback.img"", ""dll_path"": ""C:/tools/rawCopyXsector.dll""}"
            Case "/ewf/export"
                Return "{""images"": [""/cases/disk.E01""], ""format"": ""raw"", ""target"": ""/exports/disk_raw"", ""no_prompt"": true}"
            Case "/ewf/verify"
                Return "{""images"": [""/cases/disk.E01""], ""hash"": [""md5"", ""sha1""]}"
            Case "/ewf/recover"
                Return "{""images"": [""/cases/corrupted.E01""], ""target"": ""/recovered/case001""}"
            Case "/ewf/mount"
                Return "{""images"": [""/cases/disk.E01""], ""mount_point"": ""/mnt/e01""}"
            Case "/ewf/unmount"
                Return "{""mount_point"": ""/mnt/e01""}"
            Case "/ewf/mounts"
                Return "{}"
            Case "/ewf/debug"
                Return "{""images"": [""/cases/disk.E01""], ""verbose"": true}"
            Case "/read/info"
                Return "{""images"": [""/cases/disk.E01""]}"
            Case "/read/ls"
                Return "{""images"": [""/cases/disk.E01""], ""path"": ""/""}"
            Case "/read/tree"
                Return "{""images"": [""/cases/disk.E01""], ""path"": ""/"", ""max_depth"": 3}"
            Case "/read/cat"
                Return "{""images"": [""/cases/disk.E01""], ""internal_path"": ""/Windows/System32/drivers/etc/hosts""}"
            Case "/read/extract"
                Return "{""images"": [""/cases/disk.E01""], ""internal_path"": ""/Users/Test/Desktop"", ""output"": ""/tmp/extracted""}"
            Case Else
                Return "{}"
        End Select
    End Function

    Private Async Function CopiaDiscoInFileAsync(sourceDisk As String, targetFilePath As String) As Task(Of Boolean)
        Dim logBuilder As New Text.StringBuilder()
        Dim logPath As String = System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "log.txt")
        Dim success As Boolean = True

        Try
            Using sourceStream As New FileStream(sourceDisk, FileMode.Open, FileAccess.Read)
                Using targetStream As New FileStream(targetFilePath, FileMode.Create, FileAccess.Write)
                    Dim buffer(8192 * 1024 - 1) As Byte ' 8 MB buffer
                    Dim totalBytesRead As Long = 0
                    Dim totalSize As Long = sourceStream.Length

                    If totalSize = 0 Then
                        Throw New Exception("Il disco selezionato � vuoto o non accessibile.")
                    End If

                    ProgressBar1.Value = 0
                    ProgressBar1.Maximum = 100

                    Log("Inizio creazione dell'immagine disco.")
                    logBuilder.AppendLine("Inizio creazione dell'immagine disco.")

                    Do While totalBytesRead < totalSize
                        Dim remainingBytes As Long = totalSize - totalBytesRead
                        Dim toRead As Integer = If(remainingBytes > buffer.Length, buffer.Length, CInt(remainingBytes))
                        Dim zeroBuffer(toRead - 1) As Byte

                        Dim bytesRead As Integer = 0
                        Dim errorOccurred As Boolean = False
                        Dim errorMessage As String = ""

                        Try
                            bytesRead = Await sourceStream.ReadAsync(buffer, 0, toRead)
                        Catch exRead As IOException
                            errorOccurred = True
                            errorMessage = exRead.Message
                            bytesRead = toRead ' simuliamo lettura per avanzare
                        End Try

                        If errorOccurred Then
                            Await targetStream.WriteAsync(zeroBuffer, 0, zeroBuffer.Length)
                            Dim errore As String = $"Errore di lettura a byte {totalBytesRead} (blocco {toRead}): {errorMessage}"
                            Log(errore)
                            logBuilder.AppendLine(errore)
                        ElseIf bytesRead > 0 Then
                            Await targetStream.WriteAsync(buffer, 0, bytesRead)
                        End If

                        totalBytesRead += bytesRead

                        ' Calcolo percentuale con Long per evitare overflow
                        Dim percentComplete As Long = (totalBytesRead * 100) / totalSize
                        Dim percentInt As Integer = If(percentComplete > 100, 100, CInt(percentComplete))
                        ProgressBar1.Value = percentInt

                        Dim stato As String = $"Copiati {totalBytesRead} byte su {totalSize} ({percentInt}%)"
                        Log(stato)
                        logBuilder.AppendLine(stato)
                    Loop

                    Log("Backup completato con successo.")
                    logBuilder.AppendLine("Backup completato con successo.")
                End Using
            End Using

        Catch ex As Exception
            Dim msg = $"Errore durante il backup: {ex.Message}"
            Log(msg)
            logBuilder.AppendLine(msg)
            success = False

        Finally
            ProgressBar1.Value = 0
            File.WriteAllText(logPath, logBuilder.ToString())
        End Try

        Return success
    End Function






    Private Sub Button2_Click(sender As Object, e As RoutedEventArgs)
        CaricaDischi()
    End Sub

    Private Sub Button3_Click(sender As Object, e As RoutedEventArgs)
        Dim saveFileDialog As New SaveFileDialog()
        saveFileDialog.Filter = "File immagine (*.img)|*.img"
        saveFileDialog.Title = "Seleziona dove salvare il backup"

        If saveFileDialog.ShowDialog() = True Then
            TextBoxFilePath.Text = saveFileDialog.FileName
        End If
    End Sub

    Private Async Sub Button1_Click(sender As Object, e As RoutedEventArgs)
        If ComboBox1.SelectedItem Is Nothing OrElse String.IsNullOrWhiteSpace(TextBoxFilePath.Text) Then
            MessageBox.Show("Seleziona un disco sorgente e un percorso di destinazione!", "Errore", MessageBoxButton.OK, MessageBoxImage.Warning)
            Return
        End If

        Dim sourceDisk As String = GetSelectedSourceDisk()
        Dim targetFilePath As String = TextBoxFilePath.Text

        If File.Exists(targetFilePath) Then
            Dim result = MessageBox.Show("Il file esiste gi�. Vuoi sovrascriverlo?", "Attenzione", MessageBoxButton.YesNo, MessageBoxImage.Warning)
            If result = MessageBoxResult.No Then Return
        End If

        Button1.IsEnabled = False
        Dim backupOk = Await CopiaDiscoInFileAsync(sourceDisk, targetFilePath)

        If Not backupOk AndAlso CheckBoxAutoFallback.IsChecked = True Then
            Log("Backup principale fallito: avvio fallback automatico.")
            Await RunAutoFallbackSequenceAsync()
        End If

        Button1.IsEnabled = True
    End Sub

    Private Async Function RunAutoFallbackSequenceAsync() As Task
        Dim mode As String = "API poi C++"
        If ComboBoxAutoFallbackMode.SelectedItem IsNot Nothing Then
            mode = CType(ComboBoxAutoFallbackMode.SelectedItem, ComboBoxItem).Content.ToString()
        End If

        Dim apiPayload = BuildRawCopyPayload()
        Dim cppPayload = BuildRawCppPayload()
        Dim ok As Boolean = False

        Select Case mode
            Case "Solo API"
                ok = Await PostEndpointWithResultAsync("/ewf/rawCopyXsector", apiPayload)
            Case "Solo C++"
                ok = Await PostEndpointWithResultAsync("/ewf/rawCopyXsectorCpp", cppPayload)
            Case "C++ poi API"
                ok = Await PostEndpointWithResultAsync("/ewf/rawCopyXsectorCpp", cppPayload)
                If Not ok Then
                    Log("Fallback C++ fallito, provo fallback API.")
                    ok = Await PostEndpointWithResultAsync("/ewf/rawCopyXsector", apiPayload)
                End If
            Case Else
                ok = Await PostEndpointWithResultAsync("/ewf/rawCopyXsector", apiPayload)
                If Not ok Then
                    Log("Fallback API fallito, provo fallback C++.")
                    ok = Await PostEndpointWithResultAsync("/ewf/rawCopyXsectorCpp", cppPayload)
                End If
        End Select

        If ok Then
            Log("Fallback automatico completato con successo.")
        Else
            Log("Fallback automatico non riuscito.")
        End If
    End Function

    Private Async Sub ButtonHealth_Click(sender As Object, e As RoutedEventArgs)
        Await GetEndpointAsync("/health")
    End Sub

    Private Async Sub ButtonMenu_Click(sender As Object, e As RoutedEventArgs)
        Await GetEndpointAsync("/menu")
    End Sub

    Private Async Sub ButtonExecuteEndpoint_Click(sender As Object, e As RoutedEventArgs)
        If ComboBoxEndpointSelector.SelectedItem Is Nothing Then
            MessageBox.Show("Seleziona un endpoint.", "Info", MessageBoxButton.OK, MessageBoxImage.Information)
            Return
        End If

        Dim selected = CType(ComboBoxEndpointSelector.SelectedItem, EndpointItem)
        If selected.Metodo = "GET" Then
            Await GetEndpointAsync(selected.Path)
            Return
        End If

        Dim payload = TextBoxPayload.Text.Trim()
        If String.IsNullOrWhiteSpace(payload) Then
            payload = "{}"
        End If

        Try
            JsonDocument.Parse(payload)
        Catch ex As Exception
            MessageBox.Show("Payload JSON non valido: " & ex.Message, "Errore JSON", MessageBoxButton.OK, MessageBoxImage.Error)
            Return
        End Try

        Await PostEndpointAsync(selected.Path, payload)
    End Sub

    Private Async Sub ButtonRawApi_Click(sender As Object, e As RoutedEventArgs)
        If ComboBox1.SelectedItem Is Nothing OrElse String.IsNullOrWhiteSpace(TextBoxFilePath.Text) Then
            MessageBox.Show("Seleziona disco sorgente e output.", "Errore", MessageBoxButton.OK, MessageBoxImage.Warning)
            Return
        End If

        Dim payload = BuildRawCopyPayload()
        Await PostEndpointWithResultAsync("/ewf/rawCopyXsector", payload)
    End Sub

    Private Async Sub ButtonRawCpp_Click(sender As Object, e As RoutedEventArgs)
        If ComboBox1.SelectedItem Is Nothing OrElse String.IsNullOrWhiteSpace(TextBoxFilePath.Text) Then
            MessageBox.Show("Seleziona disco sorgente e output.", "Errore", MessageBoxButton.OK, MessageBoxImage.Warning)
            Return
        End If

        Dim payload = BuildRawCppPayload()
        Await PostEndpointWithResultAsync("/ewf/rawCopyXsectorCpp", payload)
    End Sub

    Private Sub ButtonRawCppBrowseDll_Click(sender As Object, e As RoutedEventArgs)
        Dim openDialog As New OpenFileDialog()
        openDialog.Filter = "DLL files (*.dll)|*.dll|All files (*.*)|*.*"
        openDialog.Title = "Seleziona DLL RawCopyXsector"
        If openDialog.ShowDialog() = True Then
            TextBoxRawCppDllPath.Text = openDialog.FileName
        End If
    End Sub

    Private Sub ButtonRawCppAutoDetectDll_Click(sender As Object, e As RoutedEventArgs)
        Dim detected = FindRawCopyDllPath()
        If String.IsNullOrWhiteSpace(detected) Then
            MessageBox.Show("DLL RawCopyXsector non trovata automaticamente.", "Info", MessageBoxButton.OK, MessageBoxImage.Information)
            Return
        End If
        TextBoxRawCppDllPath.Text = detected
        Log($"DLL RawCopyXsector selezionata automaticamente: {detected}")
    End Sub

    Private Sub SetPreset(path As String)
        For i As Integer = 0 To ComboBoxEndpointSelector.Items.Count - 1
            Dim item = CType(ComboBoxEndpointSelector.Items(i), EndpointItem)
            If item.Path = path Then
                ComboBoxEndpointSelector.SelectedIndex = i
                Exit For
            End If
        Next
        TextBoxPayload.Text = BuildPresetPayload(path)
    End Sub

    Private Sub ButtonPresetEwfInfo_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/ewf/info")
    End Sub

    Private Sub ButtonPresetEwfAcquire_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/ewf/acquire")
    End Sub

    Private Sub ButtonPresetEwfAcquireStream_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/ewf/acquire-stream")
    End Sub

    Private Sub ButtonPresetEwfRawCopy_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/ewf/rawCopyXsector")
    End Sub

    Private Sub ButtonPresetEwfRawCopyCpp_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/ewf/rawCopyXsectorCpp")
    End Sub

    Private Sub ButtonPresetEwfExport_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/ewf/export")
    End Sub

    Private Sub ButtonPresetEwfVerify_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/ewf/verify")
    End Sub

    Private Sub ButtonPresetEwfRecover_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/ewf/recover")
    End Sub

    Private Sub ButtonPresetEwfMount_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/ewf/mount")
    End Sub

    Private Sub ButtonPresetEwfUnmount_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/ewf/unmount")
    End Sub

    Private Sub ButtonPresetEwfMounts_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/ewf/mounts")
    End Sub

    Private Sub ButtonPresetEwfDebug_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/ewf/debug")
    End Sub

    Private Sub ButtonPresetReadInfo_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/read/info")
    End Sub

    Private Sub ButtonPresetReadLs_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/read/ls")
    End Sub

    Private Sub ButtonPresetReadTree_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/read/tree")
    End Sub

    Private Sub ButtonPresetReadCat_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/read/cat")
    End Sub

    Private Sub ButtonPresetReadExtract_Click(sender As Object, e As RoutedEventArgs)
        SetPreset("/read/extract")
    End Sub

    Private Sub Log(message As String)
        LogBox.Dispatcher.Invoke(Sub()
                                     LogBox.AppendText($"{DateTime.Now:HH:mm:ss} - {message}{Environment.NewLine}")
                                     LogBox.ScrollToEnd()
                                 End Sub)
    End Sub
End Class