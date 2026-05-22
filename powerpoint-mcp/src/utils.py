import re
import shutil
import zipfile


def strip_aspose_metadata(pptx_path: str) -> None:
    """Replace Aspose application tags with standard PowerPoint values in a saved PPTX."""
    temp_path = pptx_path + ".tmp"
    with zipfile.ZipFile(pptx_path, "r") as zin, zipfile.ZipFile(temp_path, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "docProps/app.xml":
                content = data.decode("utf-8")
                content = re.sub(
                    r"<Application>[^<]*</Application>",
                    "<Application>Microsoft Office PowerPoint</Application>",
                    content,
                )
                content = re.sub(
                    r"<AppVersion>[^<]*</AppVersion>",
                    "<AppVersion>16.0000</AppVersion>",
                    content,
                )
                data = content.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(temp_path, pptx_path)
