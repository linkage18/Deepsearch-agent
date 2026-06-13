import { UploadOutlined, FilePdfOutlined, CheckCircleOutlined } from "@ant-design/icons";
import { Button, Upload, message } from "antd";
import type { UploadFile } from "antd";
import { useState } from "react";
import { API_BASE_URL } from "../lib/config";

export function KnowledgeUpload() {
  const [uploading, setUploading] = useState(false);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [recentFiles, setRecentFiles] = useState<string[]>([]);

  async function handleUpload() {
    if (fileList.length === 0) {
      message.warning("请先选择 PDF 文件");
      return;
    }

    setUploading(true);
    const formData = new FormData();
    for (const file of fileList) {
      if (file.originFileObj) {
        formData.append("files", file.originFileObj);
      }
    }

    try {
      const resp = await fetch(`${API_BASE_URL}/api/knowledge/upload`, {
        method: "POST",
        body: formData,
      });
      const data = await resp.json();
      setRecentFiles(data.files || []);
      setFileList([]);
      message.success(`已添加到知识库: ${(data.files || []).join(", ")}`);
    } catch (err) {
      message.error("上传失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setUploading(false);
    }
  }

  return (
    <section className="console-panel" style={{ marginTop: 12 }}>
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">KNOWLEDGE BASE</span>
          <h2 style={{ fontSize: 15, margin: "2px 0 0" }}>知识库管理</h2>
        </div>
      </div>

      <Upload
        multiple
        accept=".pdf"
        beforeUpload={() => false}
        fileList={fileList}
        onChange={(info) => setFileList(info.fileList)}
        showUploadList={{ showPreviewIcon: false, showRemoveIcon: true }}
      >
        <Button
          block
          className="composer-icon-button"
          icon={<FilePdfOutlined />}
          style={{ marginBottom: 8, textAlign: "left", justifyContent: "flex-start" }}
        >
          选择 PDF 添加到知识库
        </Button>
      </Upload>

      <Button
        block
        className="secondary-action"
        icon={uploading ? undefined : <UploadOutlined />}
        loading={uploading}
        onClick={handleUpload}
        disabled={fileList.length === 0}
        style={{ marginTop: 4 }}
      >
        {uploading ? "上传并重建索引..." : "上传到知识库"}
      </Button>

      {recentFiles.length > 0 && (
        <ul className="uploaded-list" aria-label="已上传到知识库" style={{ marginTop: 8 }}>
          {recentFiles.map((name) => (
            <li key={name}>
              <CheckCircleOutlined style={{ color: "var(--verdigris)", marginRight: 6 }} />
              {name}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
