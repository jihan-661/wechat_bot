"""命令模块目录。

每个模块在顶层暴露 GROUPS 列表（元素为 CommandGroup 子类），
由 CommandManager.discover() 自动导入并注册。
新增一条命令只需在本目录新建模块，不需要修改任何其他文件。
"""
