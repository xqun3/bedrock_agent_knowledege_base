# bedrock_agent_konwledege_base

### Demo 介绍
模拟开发票业务，业务流程如下所示<br>

收集开票信息 -》 生成发票信息预览 -》确认后正式生成发票 -》 自动发送发票邮件 <br>


### 代码结构说明 
```
├── README.md
├── conf
│   ├── DejaVuSansCondensed.ttf                          # PDF 字体文件
│   ├── invoice_service_schema.json                      # Lambda API schema
│   └── product_code_name_map.txt                        # demo 配置文件
├── invoice_lambda.py                                    # demo 业务代码实现文件，主要lambda function
├── invoice_lambda_layer.zip                             # demo python 依赖包，lambda layer
├── notebooks
│   ├── bedrock_agent_example.ipynb                      # 完整创建 Agent
│   ├── bedrock_knowledge_base_aos_serveless.ipynb       # 自建 AOS
│   └── knowledge_base.ipynb                             # 完整创建 knowledge base
└── requirements.txt
```

### Enviroment
基础环境：python 3.11

#### python 依赖打包
本demo代码已经有打包好的lambda_layer文件，直接上传S3即可

如果有自己需要打包其他依赖，可使用 lambda image 安装依赖库, 上传到 lambda_layer<br>
reference link :https://repost.aws/knowledge-center/lambda-layer-simulated-docker <br>

可以找一台EC2，在EC2的Linux环境打包，命令如下
```
mkdir layer
cp requirements.txt layer/requirements.txt
docker run -ti -v $(pwd)/layer:/app -w /app --entrypoint /bin/bash public.ecr.aws/lambda/python:3.11 -c "pip3 install --taget ./python -r requirements.txt"
zip -r lambda_layer.zip python
```

### 上传 conf 文件到 s3 bucket
- Console 上传

### 开通 AWS SES 服务
1. verify 邮箱，链接https://us-east-1.console.aws.amazon.com/ses/home?region=us-east-1#/get-set-up
2. 修改 send_eamil 中的 SENDER 为 verify 之后的邮箱
3. 注意测试过程中，提供的收件人邮箱最好也使用验证后的邮箱，或者参考 SES 服务进行修改


### 创建 Agent
可以有两种方式创建：
1. Console 创建
    - 创建 lambda function: 
        * 添加 invoice_lambda.py 内容到 lambda 代码编辑处
        * 添加 invoice_lambda_layer.zip 
        * 点击 deploy
    - 创建 Agent，根据 console 的指示，一步步创建关联即可，Agent instruction 可在下面找到
2. Notebook step by step 创建
    - 根据 notebook 的顺序一步步执行即可

#### Agent instructions
You are a friendly invoice assistant. When greeted, use a greeting term and "I'm an invoice assistant" to answer. Through the "InvoiceService" action group, you can offer invoice services. When generating an invoice, first collect all required invoice information from user. Then generate a temporary preview image for the user's reference. If the preview image is successfully generated, return the text_info from the function result to user. Confirm with user if they want to proceed with generating the actual invoice. If user confirms, use tools to generate an invoice. If successful, return the downloadUrl from the function result to user. This allows user to download the invoice. If user indicates the information is incorrect, ask them to provide corrected information. Confirm if the user needs the invoice sent to a designated email address. If so, email the invoice file to the address provided.

