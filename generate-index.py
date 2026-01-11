#!/usr/bin/env python3
"""
vFlow仓库索引生成器
自动扫描workflows和modules目录并生成index.json
"""

import json
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path


def normalize_workflow_id(filename):
    """从文件名获取工作流ID（去除.json扩展名）"""
    return filename.replace('.json', '') if filename.endswith('.json') else filename


def normalize_module_id(filename):
    """从文件名获取模块ID（去除.zip扩展名）"""
    return filename.replace('.zip', '') if filename.endswith('.zip') else filename


# ==================== 工作流相关函数 ====================

def validate_workflow(data, filename):
    """
    验证工作流数据
    返回: (is_valid, error_message, cleaned_data)
    """
    # 检查是否有_meta
    if '_meta' not in data:
        return False, f"缺少 '_meta' 字段", None

    meta = data['_meta']

    # 验证_meta必需字段
    required_meta_fields = ['id', 'name', 'description', 'author', 'version', 'vFlowLevel']
    missing_fields = [field for field in required_meta_fields if field not in meta]

    if missing_fields:
        return False, f"_meta缺少必需字段: {', '.join(missing_fields)}", None

    # 验证_meta中的ID与文件名一致
    expected_id = normalize_workflow_id(filename)
    meta_id = meta['id']

    if meta_id != expected_id:
        return False, f"_meta.id 不匹配: 文件名='{expected_id}', _meta.id='{meta_id}'", None

    return True, None, data


def clean_workflow_for_repo(data):
    """
    清理工作流数据，准备发布到仓库
    - 将isEnabled、isFavorite、wasEnabledBeforePermissionsLost设置为false
    - 保留_meta信息
    """
    cleaned = data.copy()

    # 强制设置为false的字段
    cleaned['isEnabled'] = False
    cleaned['isFavorite'] = False
    cleaned['wasEnabledBeforePermissionsLost'] = False

    return cleaned


def scan_workflows_directory(directory_path):
    """
    扫描目录中的所有工作流JSON文件
    返回: (valid_items, errors, skipped_files)
    """
    items = []
    errors = []
    skipped_files = []

    dir_path = Path(directory_path)

    if not dir_path.exists():
        print(f"⚠️  工作流目录不存在: {directory_path}")
        return items, errors, skipped_files

    # 遍历目录中的所有JSON文件
    for filepath in dir_path.glob('*.json'):
        # 跳过index.json
        if filepath.name == 'index.json':
            continue

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 验证工作流
            is_valid, error_msg, _ = validate_workflow(data, filepath.name)

            if not is_valid:
                errors.append(f"❌ {filepath.name}: {error_msg}")
                skipped_files.append(filepath.name)
                continue

            # 提取元数据
            meta = data.get('_meta', {})

            # 清理工作流数据（保存到仓库的版本）
            cleaned_workflow = clean_workflow_for_repo(data)

            # 构建索引条目
            item = {
                'id': meta.get('id', normalize_workflow_id(filepath.name)),
                'name': meta.get('name', '未命名'),
                'description': meta.get('description', ''),
                'author': meta.get('author', '未知'),
                'version': meta.get('version', '1.0.0'),
                'vFlowLevel': meta.get('vFlowLevel', 1),
                'homepage': meta.get('homepage', ''),
                'tags': meta.get('tags', []),
                'updated_at': meta.get('updated_at', ''),
                'filename': filepath.name,
                # 构建下载URL
                'download_url': f"https://raw.githubusercontent.com/ChaoMixian/vFlow-Repos/main/workflows/{filepath.name}",
                # 本地文件路径（用于脚本更新文件）
                'local_path': str(filepath)
            }

            items.append(item)

            # 自动更新清理后的工作流文件
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(cleaned_workflow, f, ensure_ascii=False, indent=2)

            print(f"✅ {filepath.name}: {item['name']} (v{item['version']}, Level {item['vFlowLevel']})")

        except json.JSONDecodeError as e:
            errors.append(f"❌ {filepath.name}: JSON解析错误 - {str(e)}")
            skipped_files.append(filepath.name)
        except Exception as e:
            errors.append(f"❌ {filepath.name}: {str(e)}")
            skipped_files.append(filepath.name)

    return items, errors, skipped_files


# ==================== 模块相关函数 ====================

def validate_module(manifest, filename):
    """
    验证模块manifest数据
    返回: (is_valid, error_message)
    """
    # 验证必需字段
    required_fields = ['id', 'name', 'description', 'author', 'version', 'category']
    missing_fields = [field for field in required_fields if field not in manifest]

    if missing_fields:
        return False, f"manifest缺少必需字段: {', '.join(missing_fields)}"

    # 验证ID与文件名一致
    expected_id = normalize_module_id(filename)
    manifest_id = manifest['id']

    if manifest_id != expected_id:
        return False, f"manifest.id 不匹配: 文件名='{expected_id}', manifest.id='{manifest_id}'"

    return True, None


def scan_modules_directory(directory_path):
    """
    扫描目录中的所有模块ZIP文件
    返回: (valid_items, errors, skipped_files)
    """
    items = []
    errors = []
    skipped_files = []

    dir_path = Path(directory_path)

    if not dir_path.exists():
        print(f"⚠️  模块目录不存在: {directory_path}")
        return items, errors, skipped_files

    # 遍历目录中的所有ZIP文件
    for filepath in dir_path.glob('*.zip'):
        # 跳过index.json
        if filepath.name == 'index.json':
            continue

        try:
            # 打开ZIP文件
            with zipfile.ZipFile(filepath, 'r') as zip_file:
                # 查找manifest.json（可能在根目录或子目录中）
                manifest_file = None
                manifest_path = None

                for file_in_zip in zip_file.namelist():
                    if file_in_zip.endswith('manifest.json'):
                        manifest_file = file_in_zip
                        manifest_path = file_in_zip
                        break

                if manifest_file is None:
                    errors.append(f"❌ {filepath.name}: ZIP中未找到manifest.json")
                    skipped_files.append(filepath.name)
                    continue

                # 读取并解析manifest.json
                with zip_file.open(manifest_file) as manifest_json:
                    manifest = json.load(manifest_json)

                # 验证manifest
                is_valid, error_msg = validate_module(manifest, filepath.name)

                if not is_valid:
                    errors.append(f"❌ {filepath.name}: {error_msg}")
                    skipped_files.append(filepath.name)
                    continue

                # 构建索引条目
                item = {
                    'id': manifest.get('id', normalize_module_id(filepath.name)),
                    'name': manifest.get('name', '未命名'),
                    'description': manifest.get('description', ''),
                    'author': manifest.get('author', '未知'),
                    'version': manifest.get('version', '1.0.0'),
                    'category': manifest.get('category', '用户脚本'),
                    'homepage': manifest.get('homepage', ''),
                    'permissions': manifest.get('permissions', []),
                    'inputs': manifest.get('inputs', []),
                    'outputs': manifest.get('outputs', []),
                    'filename': filepath.name,
                    # 构建下载URL
                    'download_url': f"https://raw.githubusercontent.com/ChaoMixian/vFlow-Repos/main/modules/{filepath.name}",
                    # 本地文件路径（用于脚本更新文件）
                    'local_path': str(filepath)
                }

                items.append(item)

                print(f"✅ {filepath.name}: {item['name']} (v{item['version']}, {item['category']})")

        except zipfile.BadZipFile:
            errors.append(f"❌ {filepath.name}: 无效的ZIP文件")
            skipped_files.append(filepath.name)
        except json.JSONDecodeError as e:
            errors.append(f"❌ {filepath.name}: manifest.json解析错误 - {str(e)}")
            skipped_files.append(filepath.name)
        except Exception as e:
            errors.append(f"❌ {filepath.name}: {str(e)}")
            skipped_files.append(filepath.name)

    return items, errors, skipped_files


# ==================== 主函数 ====================

def generate_index(directory, item_type, scan_func, output_file='index.json'):
    """生成索引文件的通用函数"""
    print(f"🔍 扫描{item_type}目录: {directory}")
    print("=" * 60)

    # 扫描文件
    items, errors, skipped_files = scan_func(directory)

    # 打印错误和跳过的文件
    if errors:
        print("\n❌ 验证失败:")
        for error in errors:
            print(f"  {error}")

    if skipped_files:
        print(f"\n⚠️  跳过 {len(skipped_files)} 个文件")

    # 按ID排序
    items.sort(key=lambda x: x['id'])

    # 构建索引
    index = {
        'version': '1.0',
        'last_updated': datetime.now().isoformat(),
        'total_count': len(items),
        f'{item_type}': items
    }

    # 写入索引文件
    output_path = Path(directory) / output_file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"✅ 成功索引 {len(items)} 个{item_type}")
    print(f"📝 索引文件: {output_path}")
    print(f"🕐 更新时间: {index['last_updated']}")

    return len(errors) == 0


def main():
    """主函数"""
    print("🚀 vFlow 仓库索引生成器")
    print("=" * 60)

    success = True

    # 生成工作流索引
    workflows_dir = 'workflows'
    if len(sys.argv) > 1:
        workflows_dir = sys.argv[1]

    if not generate_index(workflows_dir, 'workflows', scan_workflows_directory):
        success = False

    print("\n")

    # 生成模块索引
    modules_dir = 'modules'
    if len(sys.argv) > 2:
        modules_dir = sys.argv[2]

    if not generate_index(modules_dir, 'modules', scan_modules_directory):
        success = False

    # 返回退出码
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()