# Windows EXE 安装包

输出：`dist/installers/AI-Dictionary-1.0.1-Windows-x64-Setup.exe`。

安装向导默认使用简体中文，安装至当前用户的 `%LOCALAPPDATA%\Programs\AI Dictionary`，无需管理员权限。开始菜单启动独立的 `AI Dictionary.exe`，不再要求用户运行批处理或 PowerShell 脚本。支持 Windows 设置中的卸载；个人数据 `%LOCALAPPDATA%\AIDictionary` 保留。

后端 Python 运行环境已包含。WebView2 Runtime 缺失时，安装程序运行内置的 Microsoft 官方引导程序，此步骤需要网络。当前环境已有 Runtime，实际测试没有执行缺失 Runtime 的联网安装分支。安装包尚未代码签名。

构建要求：Windows x64、Python / PyInstaller、.NET Framework C# 编译器、便携版 NSIS，以及已核验 Microsoft 签名的 `MicrosoftEdgeWebview2Setup.exe`。

```powershell
python scripts/build_windows_exe.py --makensis dist/build-tools/nsis/nsis-3.08/makensis.exe --bootstrapper dist/build-tools/MicrosoftEdgeWebview2Setup.exe
```

此次验证：静默安装到隔离测试目录；验证卸载注册信息；启动安装后的 GUI EXE 并检查查词、设置页、原生退出；卸载后程序文件与注册项移除，用户数据库哈希不变，安装目录中额外添加的文件保留。测试前原有开始菜单快捷方式已备份，测试后已恢复。

本次仅改变 Windows 安装交付方式，应用功能及其尚未实现项仍以 `BUG_REVIEW_1.0.1.md` 为准。
