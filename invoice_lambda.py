#-*- coding: utf-8 -*-
import json
import time
import os
import boto3
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from botocore.exceptions import ClientError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from fpdf import FPDF

s3 = boto3.client('s3')
bucket = os.environ.get('BUCKET_NAME')  #Name of bucket with data file and OpenAPI file
product_name_map_file = 'product_code_name_map.txt' #Location of data file in S3
product_name_map_v38_file = 'product_38_code_name_map.txt'
product_v47_to_v38_file = "product_47_to_38_map.txt"
font_lib = "DejaVuSansCondensed.ttf"
local_product_name_map_file = '/tmp/product_code_name_map.txt' #Location of data file in S3
local_product_name_map_v38_file = '/tmp/product_38_code_name_map.txt'
local_product_v47_to_v38_file = "/tmp/product_47_to_38_map.txt"
s3.download_file(bucket, product_name_map_file, local_product_name_map_file)
s3.download_file(bucket, product_name_map_v38_file, local_product_name_map_v38_file)
s3.download_file(bucket, product_v47_to_v38_file, local_product_v47_to_v38_file)
s3.download_file(bucket, font_lib, "/tmp/"+font_lib)


def get_named_parameter(event, name):
    return next(item for item in event['parameters'] if item['name'] == name)['value']

def get_named_property(event, name):
    return next(item for item in event['requestBody']['content']['application/json']['properties'] if item['name'] == name)['value']


def create_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font('DejaVu', '', '/tmp/DejaVuSansCondensed.ttf', uni=True)
    pdf.set_font('DejaVu', '', 14)
    # pdf.set_font("Arial", size=12)
    for key, value in data.items():
        print(key, value)
        pdf.cell(200, 10, txt=f"{key}: {value}", ln=1, align="C")
    file_path = "/tmp/invoice.pdf"
    pdf.output(file_path)
    s3_client = boto3.client('s3')
    s3_client.upload_file(file_path, bucket, file_path)
    return  file_path

user_info = {
            "id": "000001",
            "name": "Xiaoqun",
            "email": "test1@163.com",
            "drawer": "Xiaoqun",
            "reviewer": "Sam",
            "payee": "Lili",
            "phone": "0755-0000000",
            "address": "Qiantan, Shanghai",
            "card_name": "Amazon",
            "card_number": "00000000000000",
            "company_name": "Amazon",
            "tax_number": "440301999999980"
}

## 函数设置
functions_configs = {
    "get_product_code":
        {
            
            "product_name_map_file": local_product_name_map_file,
            "product_name_map_v38_file": local_product_name_map_v38_file,
            "product_v47_to_v38_file": local_product_v47_to_v38_file
        }
}

# 导入商品名称映射表以及商品税率映射表
product_name_map = {}
product_tax_map = {}
with open(functions_configs["get_product_code"]["product_name_map_file"],encoding="utf-8") as f:
    for line in f.readlines():
        line = line.strip()
        if line:
            code,name,tax = line.split("\t")
            product_name_map[code] = name
            product_tax_map[code] = min([float(tax_ins.strip('%')) / 100 for tax_ins in tax.split("、")])

# 映射表内容更新,支持38版编码
product_name_map_38 = {}
product_tax_map_38 = {}
with open(functions_configs["get_product_code"]["product_name_map_v38_file"],encoding="utf-8") as f:
    for line in f.readlines():
        line = line.strip()
        if line:
            code,name,tax = line.split("\t")
            product_name_map_38[code] = name
            product_tax_map_38[code] = min([float(tax_ins.strip('%')) / 100 for tax_ins in tax.split("、")])
#更新映射表
product_name_map.update(product_name_map_38)
product_tax_map.update(product_tax_map_38)

product_47_to_38_map = {}
with open(functions_configs["get_product_code"]["product_v47_to_v38_file"],encoding="utf-8") as f:
    for line in f.readlines():
        line = line.strip()
        if line:
            code47,code38 = line.split("\t")
            product_47_to_38_map[code47] = code38

def send_eamil(recipient: str, s3_file_path: str):
    # for test, we set Sender to recipient 
    SENDER = recipient
    RECIPIENT = recipient

    AWS_REGION = "us-east-1"
    SUBJECT = "Invoice Info"
    
    BODY_TEXT = "Hello,\r\nInvoice has been generated, please check out attachment."

    # Download the S3 file to a temporary location
    tmp_file_path = '/tmp/' + os.path.basename(s3_file_path)
    s3.download_file(bucket, s3_file_path, tmp_file_path)

    ATTACHMENT = tmp_file_path

    # The HTML body of the email.
    BODY_HTML = """\
    <html>
    <head></head>
    <body>
    <h1>Hello!</h1>
    <p>Invoice generate successfully! Please see the attached file for invoice info.</p>
    </body>
    </html>
    """

    CHARSET = "utf-8"
    client = boto3.client('ses',region_name=AWS_REGION)
    msg = MIMEMultipart('mixed')

    msg['Subject'] = SUBJECT 
    msg['From'] = SENDER 
    msg['To'] = RECIPIENT

    msg_body = MIMEMultipart('alternative')
    textpart = MIMEText(BODY_TEXT.encode(CHARSET), 'plain', CHARSET)
    htmlpart = MIMEText(BODY_HTML.encode(CHARSET), 'html', CHARSET)
    msg_body.attach(textpart)
    msg_body.attach(htmlpart)

    att = MIMEApplication(open(ATTACHMENT, 'rb').read())

    att.add_header('Content-Disposition','attachment',filename=os.path.basename(ATTACHMENT))
    msg.attach(msg_body)
    msg.attach(att)
    try:
        response = client.send_raw_email(
            Source=SENDER,
            Destinations=[
                RECIPIENT
            ],
            RawMessage={
                'Data':msg.as_string(),
            },
        )
    # Display an error if something goes wrong.	
    except ClientError as e:
        print(e.response['Error']['Message'])
        return {"errcode": e.response['Error']['Message']} 
    else:
        print("Email sent! Message ID:"),
        print(response['MessageId'])
        return {"errcode": "0000", "MessageId": response['MessageId']} 


def generatePreviewInvoiceImage(event):
    """This function generates a preview invoice image"""
    function_name = "generate_preview_invoice_image"
    print(f"calling method: {function_name}")

    user_id = get_named_parameter(event, 'user_id') 
    product_detail = get_named_parameter(event, 'product_detail')
    buyer_company_name = get_named_parameter(event, 'buyer_company_name')
    buyer_tax_number = get_named_parameter(event, 'buyer_tax_number')
    try:
        invoice_type = get_named_parameter(event, 'invoice_type')
    except:
        invoice_type = "全电普通发票"
    
    try:
        remark = get_named_parameter(event, 'remark')
    except:
        remark = ""

    print ("parameters ==> ", "user_id:", user_id, "product_detail:", product_detail, "buyer_company_name:", buyer_company_name, "buyer_tax_number:", buyer_tax_number, "invoice_type:", invoice_type, "remark:", remark )
    ## request 设置

    print("---------generate preview invoice---------------------")

    ## 发票基础信息设置
    # assert user_id in user_info, f"user id <{user_id}>  does not exist."
    seller_company_name = user_info["company_name"]
    seller_tax_number = user_info["tax_number"]
    drawer = user_info.get("drawer","")
    issue_date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    temp_invoice_number = "00000000"
    new_res = {}
    new_res["input_args"] = {}
    new_res["input_args"]["product_detail"] = product_detail
    new_res["input_args"]["buyer_company_name"] = buyer_company_name
    new_res["input_args"]["buyer_tax_number"] = buyer_tax_number
    new_res["input_args"]["invoice_type"] = invoice_type
    new_res["input_args"]["remark"] = remark
    ## 发票重要信息设置
    ### 1. 发票种类
    invoice_type_map = {"全电普通发票": "26", "全电专用发票": "27"}
    invoice_type_num = invoice_type_map.get(invoice_type, None)
    if invoice_type_num is None:
        new_res["status"] = "fail"
        new_res["results"] = f"发票种类<{invoice_type}>填错了，目前只支持'全电普通发票'和'全电专用发票'，请进行修改."
        return new_res
    ### 2. 商品明细、不计税的总金额、总税额设置
    itemlist = []
    invoice_amounts = 0 #不计税的总金额
    tax_amounts = 0 #总税额
    
    if isinstance(product_detail,str):
        product_detail = product_detail.replace('\"', '"')
        product_detail = product_detail.replace('["{', '[{')
        product_detail = product_detail.replace('}"]', '}]')
        product_detail = eval(product_detail)

    print(f"After process product_detail: {product_detail}")

    for product in product_detail:
        if isinstance(product["money"],str):
            product["money"] = product["money"].strip()
            try:
                product["money"] = int(product["money"])
            except:
                product["money"] = float(product["money"])
        product_total_amount = '{:.2f}'.format(product["money"])  # 每个商品的总金额
        tax_rate = product_tax_map.get(product["code"], None) #税率
        if tax_rate is None:
            new_res["status"] = "fail"
            new_res["results"] = f"您提供的商品<{product['name']}>的税收编码<{product['code']}>是错误的，请进行修改."
            return new_res
        product_amount = '{:.2f}'.format(float(product_total_amount) / (1 + tax_rate))  # 每个商品去掉税额的原始金额
        tax_amount = '{:.2f}'.format(float(product_amount) * tax_rate)#每个商品的税额
        invoice_amounts += float(product_amount)
        tax_amounts += float(tax_amount)

        itemlist.append({
            "goodsName": product["name"],
            "specModel": "",
            "unit": "",
            "num": "",
            "unitPrice": "",
            "detailAmount": product_amount,
            "taxRate": '{:.2f}'.format(tax_rate),
            "taxAmount": tax_amount,
            "zeroTaxRateFlag": ""
            })
        
    data = {
        "clientId": "testClinetId",
        "appName": "开票",
        "invoiceType": invoice_type_num,
        "invoiceNo": temp_invoice_number,
        "issueTime": issue_date,
        "buyerName": buyer_company_name,
        "buyerTaxNo": buyer_tax_number,
        "salerName": seller_company_name,
        "salerTaxNo": seller_tax_number,
        "remark": remark,
        "drawer": drawer,
        "invoiceAmount": '{:.2f}'.format(invoice_amounts),
        "totalTaxAmount": '{:.2f}'.format(tax_amounts),
        "totalAmount": '{:.2f}'.format(invoice_amounts+tax_amounts),
    }

    result = {
                "input_args": {
                    "product_detail":product_detail,
                    "buyer_company_name": buyer_company_name,
                    "buyer_tax_number": buyer_tax_number,
                    "invoice_type": invoice_type,
                },
                "status": "success",
                "results": {
                    "text_info": data
                }
            }

    return result


def issueInvoice(event):
    """This function is used to issue invoices"""
    ## request参数 设置
    print("------------issue_invoice----------------")
    function_name = "issue_invoice"
    print(f"calling method: {function_name}")

    user_id = get_named_parameter(event, 'user_id') 
    product_detail = get_named_parameter(event, 'product_detail')
    buyer_company_name = get_named_parameter(event, 'buyer_company_name')
    buyer_tax_number = get_named_parameter(event, 'buyer_tax_number')
    
    try:
        invoice_type = get_named_parameter(event, 'invoice_type')
    except:
        invoice_type = "全电普通发票"
    
    try:
        remark = get_named_parameter(event, 'remark')
    except:
        remark = ""
    
    print ("parameters ==> ", "user_id:", user_id, "product_detail:", product_detail, "buyer_company_name:", buyer_company_name, "buyer_tax_number:", buyer_tax_number, "invoice_type:", invoice_type, "remark:", remark )


    ## 发票基础信息设置
    reviewer = user_info.get("reviewer", "")
    payee = user_info.get("payee", "")
    seller_address = user_info.get("address", "")
    seller_phone = user_info.get("phone", "")
    seller_account = user_info.get("card_name", "") + user_info.get("card_number", "")
    seller_cardname = user_info.get("card_name", "")
    seller_cardnumber = user_info.get("card_number", "")
    # seller_company_name = user_info["company_name"]
    seller_tax_number = user_info["tax_number"]
    #初始化输出
    
    res = {}
    res["input_args"] = {}
    res["input_args"]["product_detail"] = product_detail
    res["input_args"]["buyer_company_name"] = buyer_company_name
    res["input_args"]["buyer_tax_number"] = buyer_tax_number
    res["input_args"]["invoice_type"] = invoice_type
    res["input_args"]["remark"] = remark
    ## 发票重要信息设置
    ### 1. 发票种类
    invoice_type_map = {"全电普通发票": "1", "全电专用发票": "2"}
    invoice_type_num = invoice_type_map.get(invoice_type, None)
    if invoice_type_num is None:
        res["status"] = "fail"
        res["results"] = f"发票种类<{invoice_type}>填错了，目前只支持'全电普通发票'和'全电专用发票'，请进行修改."
        return res
    ### 2. 商品明细、不计税的总金额、总税额设置
    itemlist = []
    invoice_amounts = 0 #不计税的总金额
    tax_amounts = 0 #总税额
    
    if isinstance(product_detail,str):
        product_detail = product_detail.replace('\"', '"')
        product_detail = product_detail.replace('["{', '[{')
        product_detail = product_detail.replace('}"]', '}]')
        product_detail = eval(product_detail)
        
    print(f"After process product_detail: {product_detail}")
    
    for product in product_detail:
        if isinstance(product["money"], str):
            product["money"] = product["money"].strip()
            try:
                product["money"] = int(product["money"])
            except:
                product["money"] = float(product["money"])
        product["code"] = product_47_to_38_map[product["code"]] \
            if product["code"] in product_47_to_38_map \
            else product["code"]
        product_total_amount = '{:.2f}'.format(product["money"])  # 每个商品的总金额
        tax_rate = product_tax_map.get(product["code"], None) #税率
        if tax_rate is None:
            res["status"] = "fail"
            res["results"] = f"您提供的商品<{product['name']}>的税收编码<{product['code']}>是错误的，请进行修改."
            return res
        product_amount = '{:.2f}'.format(float(product_total_amount) / (1 + tax_rate))  # 每个商品去掉税的原始金额
        tax_amount = '{:.2f}'.format(float(product_amount) * tax_rate) #每个商品的税额
        invoice_amounts += float(product_amount)
        tax_amounts += float(tax_amount)
        itemlist.append({
            "specModel": "",
            "zeroTaxRateFlag": "",
            "taxAmount": tax_amount,
            "taxRate": '{:.2f}'.format(tax_rate),
            "goodsCode": product["code"],
            "detailAmount": product_amount,
            "discountType": "0",
            "goodsName": product["name"],
            "preferentialPolicy": "0",
            "vatException": ""
        })
    # 创建invoice_info
    invoice_info = {
        "taxFlag": "0",
        "inventoryFlag": "0",
        "inventoryProjectName": "0",
        "salerAddress": seller_address,
        "salerPhone": seller_phone,
        "salerAccount": seller_account,
        "salerCardName": seller_cardname,
        "salerCardNumber": seller_cardnumber,
        "salerTaxNo": seller_tax_number,
        "buyerName": buyer_company_name,
        "buyerTaxNo": buyer_tax_number,
        "invoiceAmount": '{:.2f}'.format(invoice_amounts),
        "totalAmount": '{:.2f}'.format(invoice_amounts + tax_amounts),
        "totalTaxAmount": '{:.2f}'.format(tax_amounts),
        "type": "0",
        "reviewer": reviewer,
        "payee": payee,
        "originalInvoiceCode": "",
        "originalInvoiceNo": "",
        "invoiceType": invoice_type_num,
        "invoiceNo": "92698367",
        "invoiceCode": "050001901011",
        "serialNo": "9a8b0aa715314c327380"
    }

    file_path = create_pdf(invoice_info)
    
    result = {
                "input_args": {
                    "product_detail":product_detail,
                    "buyer_company_name": buyer_company_name,
                    "buyer_tax_number": buyer_tax_number,
                    "invoice_type": invoice_type,
                    "remark": ""
                },
                "status": "success",
                "results": {
                    "downloadUrl": file_path,
                }
            }
    return result


def sendInvoiceEmail(event):
    """This function send the issued invoice file link to a specified email address"""
    ## request参数 设置
    print("------------send email----------------")
    function_name = "send_invoice_email"
    print(f"calling method: {function_name}")
    print(f"Event: \n {json.dumps(event)}")

    invoice_code = get_named_parameter(event, 'invoice_code') 
    invoice_number = get_named_parameter(event, 'invoice_number')
    email_address = get_named_parameter(event, 'email_address')

    print ("parameters ==> ", "invoice_code:", invoice_code, "invoice_number:", invoice_number, "email_address:", email_address)
    
    result = send_eamil(email_address, "/tmp/invoice.pdf")

    #定义输出
    res = {}
    res["input_args"] = {}
    res["input_args"]["invoice_code"] = invoice_code
    res["input_args"]["invoice_number"] = invoice_number
    res["input_args"]["email_address"] = email_address
    if result["errcode"] == "0000":
        res["status"] = "success"
        res["results"] = "邮件发送成功"
    else:
        res["status"] = "fail"
        res["results"] = f"{result['errcode']}\n邮件发送失败,请稍后尝试重新发送."
    print(res)
    return res


def lambda_handler(event, context):

    result = ''
    response_code = 200
    action_group = event['actionGroup']
    api_path = event['apiPath']
    
    print ("lambda_handler == > api_path: ",api_path)
    
    if api_path == '/generatePreviewInvoiceImage':
        result = generatePreviewInvoiceImage(event)
    elif api_path == '/issueInvoice':
        result = issueInvoice(event)
    elif api_path == '/sendInvoiceEmail':
        result = sendInvoiceEmail(event) 
    else:
        response_code = 404
        result = f"Unrecognized api path: {action_group}::{api_path}"

    response_body = {
        'application/json': {
            'body': json.dumps(result)
        }
    }
    
    session_attributes = event['sessionAttributes']
    prompt_session_attributes = event['promptSessionAttributes']
    
    print ("Event:", event)
    action_response = {
        'actionGroup': event['actionGroup'],
        'apiPath': event['apiPath'],
        # 'httpMethod': event['HTTPMETHOD'], 
        'httpMethod': event['httpMethod'], 
        'httpStatusCode': response_code,
        'responseBody': response_body,
        'sessionAttributes': session_attributes,
        'promptSessionAttributes': prompt_session_attributes
    }

    api_response = {'messageVersion': '1.0', 'response': action_response}
        
    return api_response